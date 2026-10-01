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
    python3 pipeline/vision_api.py --check                       # 预检配置齐备（不发请求）
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

# 凭据形状：网关回显的 key 未必等于本地那把（子 key / 已轮换的旧 key），
# 落盘前一律按形状兜底抹掉。宁可多抹一点，也不能让它跟着 out.jsonl 进仓库。
SECRET_SHAPE_RE = re.compile(
    r"\b(?:sk|pk|rk|ak)-[A-Za-z0-9_\-]{8,}"      # 常见厂商前缀
    r"|\bgh[pousr]_[A-Za-z0-9]{16,}"            # GitHub 令牌
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"          # Slack 令牌
    r"|\bAIza[A-Za-z0-9_\-]{20,}"               # Google API Key
    r"|\bBearer\s+[A-Za-z0-9._\-]{16,}"         # 认证头
)

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
    """抹掉错误文本里的端点 URL、主机名与**凭据本身**。

    `urllib` 的异常文本自带请求 URL，网关的错误 body 也常回显 URL；更糟的是认证失败时
    往往把 key 原文带回来（`invalid api key: sk-…`）。这些字符串会随 `--batch` 的结果
    文件落盘、再被 make_figures.py 复制进 manifest.json，一旦跟着提交就等于把网关地址
    与凭据写进了开源仓库——所以凭据形状和端点一样要抹。
    """
    url = os.environ.get("VISION_API_URL", "").strip()
    if url:
        text = text.replace(url, "<endpoint>")
        host = urllib.parse.urlsplit(url).netloc
        if host:
            text = text.replace(host, "<endpoint>")
    # 先抹环境变量里的真实 key（最准），再兜住没进环境变量、只出现在错误 body 里的形状
    for name in ("VISION_API_KEY", "VISION_TOKEN"):
        secret = os.environ.get(name, "").strip()
        if secret:
            text = text.replace(secret, "<credential>")
    # 网关回显的 key 未必等于本地那把（子 key / 已轮换的旧 key），按形状兜底
    text = SECRET_SHAPE_RE.sub("<credential>", text)
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
            # 网关在 CDN 后面：默认的 Python-urllib UA 会被边缘防护拦截
            # （注意：本文件也在隐私闸门的扫描范围内，注释里不要写任何非白名单主机名）
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
                    # [P1] 读缓存用调用方的 max_tokens 算键、写缓存用重试中翻倍后的值算键，
                    # 于是被截断后成功的那次永远命不中原调用的键：每次重跑都重新计费，
                    # 缓存形同虚设。写缓存必须用**读缓存时用的那个键**。
                    cp.write_text(json.dumps(
                        {"model": model, "tag": tag, "system": system, "prompt": prompt,
                         # 键是按**调用方**的 max_tokens 算的，这里必须记同一个值；
                         # 记 payload 里翻倍后的值会与文件所在的位置对不上，看着像 bug。
                         "max_tokens": max_tokens,
                         # 实际发出的是抬高后的值，单独记，别混为一谈
                         "max_tokens_used": payload["max_tokens"],
                         "response": content,
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


def check() -> int:
    """预检：只验配置完备性，**不发任何模型请求**（因此免费、可当 CI 闸门用）。

    为什么需要它：端点/模型/凭据全靠环境变量注入，缺一项时批处理会在跑到一半才抛
    「缺少 VISION_MODEL」——那时任务文件已经生成、缓存目录已经建好，操作者却以为自己
    只差最后一步。`--check` 把这件事提前到一条命令，并且一次性列出缺哪几项。

    注意它**只验配置、不验连通性**：真要验端点可达就得发请求，那会产生计费且依赖网络。
    端点写错（比如路径少了 /chat/completions）只有真正调用才会暴露。
    """
    problems: list[str] = []
    _load_env_file()          # 幂等；.vision.env 优先于已存在的同名环境变量
    src = ENV_FILE.name if ENV_FILE.exists() else "环境变量"
    for name in ("VISION_API_URL", "VISION_MODEL"):
        if not os.environ.get(name, "").strip():
            problems.append(f"缺少 {name}")
    url = os.environ.get("VISION_API_URL", "").strip()
    if url:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https"):
            problems.append(f"VISION_API_URL 的协议是 {parts.scheme or '(空)'}，应为 http/https")
        if not parts.netloc:
            problems.append("VISION_API_URL 没有主机名")
        if not parts.path or parts.path == "/":
            problems.append("VISION_API_URL 看起来只有主机、没有接口路径"
                            "（应指向完整的 chat/completions 端点）")
    try:
        api_key()
    except SystemExit as e:
        problems.append(str(e))

    model = os.environ.get("VISION_MODEL", "").strip()
    if problems:
        print("视觉模型链路未就绪：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(f"\n配置方式：把以下变量写进仓库根目录的 {ENV_FILE.name}（该文件已 gitignore，"
              f"同名环境变量优先），或直接 export。当前读取来源：{src}。", file=sys.stderr)
        print("详见 docs/pipeline.md §3。仓库里不保存任何端点与 provider 命名。", file=sys.stderr)
        return 1
    print(f"视觉模型链路已就绪（配置来源：{src}）")
    print(f"  模型名：{model}")
    print(f"  端点：{_redact(url)}        # 输出里始终抹掉端点，避免随日志进仓库")
    print("  凭据：已配置（不回显）")
    print("  注意：本检查不验连通性；真正调用仍可能因端点路径或网络失败。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="预检端点/模型/凭据是否齐备，不发模型请求（可当闸门用）")
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

    if args.check:
        sys.exit(check())

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
        # [P0] 光按 id 复用是错的：结果记录里没有提示词/参数指纹，于是改了
        # prompts/svg-zh.md、改了术语表、或者重新抽取导致源 SVG 变化之后，
        # **上一轮的成功结果同样被无条件回写**——实测同一批 id、提示词从 V1 改成 V2
        # 后重跑，HTTP 调用数 = 0，输出仍是 V1 的内容。指纹不同就必须重跑。
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
        stale = 0

        def fingerprint(job: dict) -> str:
            # [P1] 必须用**解析后**的 model：job.get("model", args.model) 在模型来自
            # VISION_MODEL 环境变量时是 None，而 call() 会把它解析成 env 里的模型。
            # 于是「换了个模型重跑」算出的指纹与上次完全相同，旧结果被无条件复用——
            # 与 P0-9 同一个失效模式，只是换了个维度。
            model = job.get("model") or args.model or model_name()
            payload = json.dumps(
                {"prompt": job.get("prompt", ""), "system": job.get("system", args.system),
                 "model": model,
                 "max_tokens": job.get("max_tokens", args.max_tokens)},
                ensure_ascii=False, sort_keys=True)
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

        pending = []
        fp_by_id: dict[str, str] = {}
        for j in jobs:
            fp = fingerprint(j)
            fp_by_id[j.get("id", "")] = fp
            prev = done.get(j.get("id", ""))
            if prev and prev.get("fp") == fp:
                continue          # 指纹一致：复用
            if prev:
                stale += 1        # 指纹缺失或已变：必须重跑
            j["_fp"] = fp
            pending.append(j)
        if stale:
            print(f"续跑：{stale} 个旧结果缺少指纹或提示词/参数已变，将重新调用",
                  file=sys.stderr)
        if done:
            print(f"续跑：已跳过 {len(jobs) - len(pending)} 个已完成任务", file=sys.stderr)
        # 回写：只保留指纹仍然有效的旧结果。
        # 指纹过期的必须丢掉，否则 apply 会读到 V1 的旧内容（文件里出现两个同 id 记录）。
        fh = out.open("w", encoding="utf-8") if out else None
        if fh:
            for rid, rec in done.items():
                if rec.get("fp") and rec["fp"] == fp_by_id.get(rid):
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
                rec = {"id": job.get("id", ""), "ok": True, "text": text,
                       "fp": job.get("_fp", "")}
            except Exception as e:  # noqa: BLE001
                rec = {"id": job.get("id", ""), "ok": False, "error": str(e),
                       "fp": job.get("_fp", "")}
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
