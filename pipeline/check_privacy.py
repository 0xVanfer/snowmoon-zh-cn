#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""隐私闸门：扫描 git 跟踪的文本文件，阻止内部网关信息再次进仓库。

规则（刻意不写具体 provider 名，避免闸门自身成为泄漏源）：

  1. `sk-` 形状的密钥字面量；
  2. 带 `/v1/` 路径的 http(s) 端点（模型调用端点只允许经环境变量注入）；
  3. `pipeline/` 下的 Python 文件里出现非公开白名单的 http(s) 主机；
  4. 本地 `.privacy-terms`（不入库，一行一个子串，`#` 起头为注释）里列出的词——
     这台机器上跑时用它兜住已知的网关地址、harness 本机配置路径与 provider 命名，
     CI 上该文件不存在则跳过（那三条本机信息本身就不该写进这个脚本）。

用法: python3 pipeline/check_privacy.py   # 有命中则打印文件:行号并退出 1
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_TERMS = ROOT / ".privacy-terms"

SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
ENDPOINT_RE = re.compile(r"https?://[^\s\"'()<>]+/v1/")
CODE_HOST_RE = re.compile(r"https?://([A-Za-z0-9._-]+)")
# 代码里只允许这些公开主机（文档里的调研链接不在此列，见规则 4 只作用于 pipeline/*.py）
CODE_HOST_ALLOW = {
    "github.com", "0xvanfer.github.io", "snowmoon.vanfer.tech", "vitalik.eth.limo",
    "www.w3.org", "w3.org", "raw.githubusercontent.com", "localhost", "127.0.0.1",
}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, check=True).stdout
    return [ROOT / p.decode() for p in out.split(b"\0") if p]


def local_terms() -> list[str]:
    if not LOCAL_TERMS.exists():
        return []
    terms = []
    for line in LOCAL_TERMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def main() -> None:
    terms = local_terms()
    hits: list[str] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue  # 二进制文件跳过
        rel = path.relative_to(ROOT)
        for lineno, line in enumerate(text.splitlines(), 1):
            why = None
            if SECRET_RE.search(line):
                why = "疑似密钥字面量"
            elif ENDPOINT_RE.search(line):
                why = "硬编码的 /v1/ 端点"
            elif rel.parts[0] == "pipeline" and rel.suffix == ".py":
                host = CODE_HOST_RE.search(line)
                if host and host.group(1) not in CODE_HOST_ALLOW:
                    why = f"代码里的非白名单主机 {host.group(1)}"
            if why is None:
                why = next((f"命中 .privacy-terms 词条「{t}」" for t in terms if t in line), None)
            if why:
                hits.append(f"{rel}:{lineno}: {why}")

    if hits:
        print("隐私闸门未通过：以下位置疑似泄漏端点 / 凭据 / provider 信息", file=sys.stderr)
        for h in hits:
            print("  " + h, file=sys.stderr)
        sys.exit(1)
    print(f"隐私闸门通过（扫描 {len(tracked_files())} 个受跟踪文件）")


if __name__ == "__main__":
    main()
