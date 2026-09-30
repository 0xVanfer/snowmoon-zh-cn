#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""视觉模型调用器（Snowmoon 中译项目专用 harness）。

端点、凭据、模型名一律从环境变量读取，仓库里不保存任何网关/provider 信息：

    VISION_API_URL        完整的 chat/completions 端点
    VISION_MODEL          模型名
    VISION_API_KEY        凭据（直接给值）
    VISION_API_KEY_FILE   或：本地凭据文件路径（`NAME: value` 形式）
    VISION_API_KEY_NAME   配合上一个使用：取该文件里的哪个键

以上变量也可以写在仓库根目录的 `.vision.env`（每行 `KEY=VALUE`，该文件已 gitignore，
同名环境变量优先）。必填项缺失时直接报错退出，不退回任何写死的默认值——这是刻意的：
端点与 provider 命名一旦进仓库就等于公开。

设计要点：
  * 结果落盘缓存（`sources/work/cache/vision/`），键为模型+系统提示+用户提示的 SHA-1，
    因此流水线可中断续跑、重跑同一图片不会重复计费；
  * 失败自动重试（网络/空回复/被 reasoning 吃满 max_tokens 时提高上限重试）；
  * 报错文本落盘前抹掉端点 URL（urllib 异常与网关错误 body 都带 URL，
    否则一次失败就把网关地址写进了结果文件）；
  * 支持单条与 JSONL 批处理两种模式。

用法:
    python3 pipeline/vision_api.py --prompt-file p.txt --out out.svg
    python3 pipeline/vision_api.py --prompt "..." --print
    python3 pipeline/vision_api.py --batch jobs.jsonl --out results.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "sources" / "work" / "cache" / "vision"
ENV_FILE = ROOT / ".vision.env"

_env_loaded = False


def _load_env_file() -> None:
    """把 `.vision.env` 读进 os.environ（不覆盖已存在的环境变量）。"""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _require(name: str) -> str:
    _load_env_file()
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(f"缺少 {name}：请设置该环境变量，或写进 {ENV_FILE.name}"
                         f"（该文件不入库；配置方式见 docs/pipeline.md §3）")
    return val


def endpoint() -> str:
    return _require("VISION_API_URL")


def model_name() -> str:
    return _require("VISION_MODEL")


def api_key() -> str:
    _load_env_file()
    key = os.environ.get("VISION_API_KEY", "").strip()
    if key:
        return key
    cred = os.environ.get("VISION_API_KEY_FILE", "").strip()
    name = os.environ.get("VISION_API_KEY_NAME", "").strip()
    if not cred or not name:
        raise SystemExit("缺少 VISION_API_KEY：请直接设置它，或设置 VISION_API_KEY_FILE + "
                         "VISION_API_KEY_NAME 指向本地凭据文件（见 docs/pipeline.md §3）")
    path = Path(cred).expanduser()
    if not path.exists():
        raise SystemExit(f"凭据文件不存在：{path}")
    # 凭据文件是 `NAME: value` 形式的 YAML（键可能缩进在 `refs:` 之下）；
    # YAML 允许 `NAME: "sk-…"`，引号必须剥掉，否则 Authorization 头会带上引号
    m = re.search(rf"^[ \t]*{re.escape(name)}:[ \t]*(\S+)",
                  path.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"凭据文件 {path} 里没有 {name}")
    return m.group(1).strip().strip('"').strip("'")


def _redact(text: str) -> str:
    """抹掉错误文本里的端点 URL 与主机名。

    `urllib` 的异常文本自带请求 URL，网关的错误 body 也常回显 URL；这些字符串会随
    `--batch` 的结果文件落盘，一旦跟着提交就等于把网关地址写进了开源仓库。
    """
    url = os.environ.get("VISION_API_URL", "").strip()
    if not url:
        return text
    text = text.replace(url, "<endpoint>")
    host = urllib.parse.urlsplit(url).netloc
    if host:
        text = text.replace(host, "<endpoint>")
    return text


def cache_path(model: str, system: str, prompt: str,
               max_tokens: int | None = None, temperature: float | None = None) -> Path:
    # max_tokens / temperature 必须进键：否则调大上限重跑仍会命中旧缓存，
    # 一次被截断的回复会被永久复用。
    h = hashlib.sha1(
        f"{model}\x00{system}\x00{prompt}\x00{max_tokens}\x00{temperature}".encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def _post(payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        endpoint(),
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key()}",
            # 网关在 Cloudflare 后面：默认的 Python-urllib UA 会被 1010 拦截
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def call(prompt: str, system: str = "", model: str | None = None,
         max_tokens: int = 32000, temperature: float | None = None,
         cache: bool = True, retries: int = 4, tag: str = "") -> str:
    model = model or model_name()
    cp = cache_path(model, system, prompt, max_tokens, temperature)
    if cache and cp.exists():
        try:
            data = json.loads(cp.read_text(encoding="utf-8"))
            if data.get("response"):
                return data["response"]
        except json.JSONDecodeError:
            pass

    messages = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature

    last = ""
    for attempt in range(retries):
        try:
            data = _post(payload)
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content") or ""
            finish = choice.get("finish_reason")
            if content.strip() and finish != "length":
                if cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cp = cache_path(model, system, prompt, payload["max_tokens"], temperature)
                    cp.write_text(json.dumps(
                        {"model": model, "tag": tag, "system": system, "prompt": prompt,
                         "max_tokens": payload["max_tokens"], "response": content,
                         "usage": data.get("usage"), "created": int(time.time())},
                        ensure_ascii=False), encoding="utf-8")
                return content
            if content.strip() and finish == "length":
                # 被 max_tokens 截断的回复**不能**当成成功：SVG/CSS/JS 截断后是废文件，
                # 而且一旦进缓存就永久复用。抬高上限重试。
                last = f"输出被 max_tokens 截断（{payload['max_tokens']}）finish_reason=length"
                payload["max_tokens"] = min(int(payload["max_tokens"] * 2), 96000)
            else:
                # 空回复：多半是 reasoning 吃满预算，抬高上限重试
                last = f"空回复 finish_reason={finish} usage={data.get('usage')}"
                payload["max_tokens"] = min(int(payload["max_tokens"] * 2), 96000)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:400]
            last = f"HTTP {e.code}: {body}"
            if e.code in (401, 403, 404):
                break
            if e.code == 400 and payload["max_tokens"] > 8000:
                # 多半是 max_tokens 超出该模型上限：降档重试
                payload["max_tokens"] = max(8000, payload["max_tokens"] // 2)
                continue
            if e.code == 400:
                break
            if e.code == 429 or e.code >= 500:
                ra = e.headers.get("Retry-After") if e.headers else None
                if ra:
                    time.sleep(min(60.0, float(ra) if ra.isdigit() else 5.0))
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(min(2 ** attempt * 2, 30))
    raise RuntimeError(f"视觉模型调用失败：{_redact(last)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--system", default="")
    ap.add_argument("--model", default=None, help="默认取环境变量 VISION_MODEL")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out")
    ap.add_argument("--print", action="store_true", dest="do_print")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--batch", help="JSONL：每行 {id, prompt, system?, max_tokens?}")
    ap.add_argument("--concurrency", type=int, default=4, help="批处理并发数")
    args = ap.parse_args()

    if args.batch:
        jobs = []
        for lineno, line in enumerate(Path(args.batch).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                jobs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"任务文件第 {lineno} 行无法解析：{e}")
        out = Path(args.out) if args.out else None
        # 续跑：读出已有的成功结果，重写一份干净的结果文件（顺带丢掉半行损坏），
        # 只跑还没成功的任务。旧实现用 "w" 打开，一启动就把上一轮结果全毁了。
        done: dict[str, dict] = {}
        if out and out.exists():
            for line in out.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("id"):
                    done[rec["id"]] = rec
        pending = [j for j in jobs if j.get("id") not in done]
        if done:
            print(f"续跑：已跳过 {len(jobs) - len(pending)} 个已完成任务", file=sys.stderr)
        fh = out.open("w", encoding="utf-8") if out else None
        if fh:
            for rec in done.values():
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
        lock = threading.Lock()
        done_n = [0]
        failures = [0]

        def run_one(job: dict) -> dict:
            try:
                text = call(job["prompt"], system=job.get("system", args.system),
                            model=job.get("model", args.model),
                            max_tokens=job.get("max_tokens", args.max_tokens),
                            cache=not args.no_cache, tag=job.get("id", args.tag))
                rec = {"id": job.get("id", ""), "ok": True, "text": text}
            except Exception as e:  # noqa: BLE001
                rec = {"id": job.get("id", ""), "ok": False, "error": str(e)}
            with lock:
                done_n[0] += 1
                if not rec["ok"]:
                    failures[0] += 1
                line = json.dumps(rec, ensure_ascii=False)
                if fh:
                    fh.write(line + "\n")
                    fh.flush()
                print(f"[{done_n[0]}/{len(pending)}] {rec['id']} {'ok' if rec['ok'] else 'FAIL'} "
                      f"{len(rec.get('text', ''))} chars", file=sys.stderr)
            return rec

        try:
            with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
                list(ex.map(run_one, pending))
        finally:
            if fh:
                fh.close()
        if failures[0]:
            print(f"{failures[0]} 个任务失败", file=sys.stderr)
            sys.exit(1)
        return

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt
    else:
        prompt = sys.stdin.read()

    text = call(prompt, system=args.system, model=args.model, max_tokens=args.max_tokens,
                cache=not args.no_cache, tag=args.tag)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    if args.do_print or not args.out:
        print(text)


if __name__ == "__main__":
    main()
