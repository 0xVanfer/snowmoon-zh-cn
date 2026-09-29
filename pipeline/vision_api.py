#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""视觉模型调用器（Snowmoon 中译项目专用 harness）。

使用 DeepSeek Harness 环境中配置的 harness 里配置的 provider（视觉模型，见
`<harness 本地 provider 配置>`）与其凭据（`<本地凭据文件>`
中的 `VISION_API_KEY`，或同名环境变量）。

设计要点：
  * 结果落盘缓存（`sources/work/cache/vision/`），键为模型+系统提示+用户提示的 SHA-1，
    因此流水线可中断续跑、重跑同一图片不会重复计费；
  * 失败自动重试（网络/空回复/被 reasoning 吃满 max_tokens 时提高上限重试）；
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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "sources" / "work" / "cache" / "vision"
CRED = Path.home() / "<harness-config-dir>" / "<local-cred-file>"
ENDPOINT = "https://<endpoint>/v1/chat/completions"
DEFAULT_MODEL = "vision-model"


def api_key() -> str:
    key = os.environ.get("VISION_API_KEY")
    if key:
        return key.strip()
    if CRED.exists():
        m = re.search(r"VISION_API_KEY:\s*(\S+)", CRED.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip()
    raise SystemExit("找不到 VISION_API_KEY（环境变量或 <本地凭据文件>）")


def cache_path(model: str, system: str, prompt: str) -> Path:
    h = hashlib.sha1(f"{model}\x00{system}\x00{prompt}".encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def _post(payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
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


def call(prompt: str, system: str = "", model: str = DEFAULT_MODEL,
         max_tokens: int = 32000, temperature: float | None = None,
         cache: bool = True, retries: int = 4, tag: str = "") -> str:
    cp = cache_path(model, system, prompt)
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
            if content.strip():
                if cache:
                    CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    cp.write_text(json.dumps(
                        {"model": model, "tag": tag, "system": system, "prompt": prompt,
                         "response": content, "usage": data.get("usage"),
                         "created": int(time.time())}, ensure_ascii=False), encoding="utf-8")
                return content
            # 空回复：多半是 reasoning 吃满预算，抬高上限重试
            last = f"空回复 finish_reason={choice.get('finish_reason')} usage={data.get('usage')}"
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
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(min(2 ** attempt * 2, 30))
    raise RuntimeError(f"视觉模型调用失败（{retries} 次）：{last}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file")
    ap.add_argument("--system", default="")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--tag", default="")
    ap.add_argument("--out")
    ap.add_argument("--print", action="store_true", dest="do_print")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--batch", help="JSONL：每行 {id, prompt, system?, max_tokens?}")
    ap.add_argument("--concurrency", type=int, default=4, help="批处理并发数")
    args = ap.parse_args()

    if args.batch:
        jobs = [json.loads(l) for l in Path(args.batch).read_text(encoding="utf-8").splitlines() if l.strip()]
        out = Path(args.out) if args.out else None
        fh = out.open("w", encoding="utf-8") if out else None
        lock = threading.Lock()
        done = [0]

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
                done[0] += 1
                line = json.dumps(rec, ensure_ascii=False)
                if fh:
                    fh.write(line + "\n")
                    fh.flush()
                print(f"[{done[0]}/{len(jobs)}] {rec['id']} {'ok' if rec['ok'] else 'FAIL'} "
                      f"{len(rec.get('text', ''))} chars", file=sys.stderr)
            return rec

        try:
            with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
                list(ex.map(run_one, jobs))
        finally:
            if fh:
                fh.close()
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
