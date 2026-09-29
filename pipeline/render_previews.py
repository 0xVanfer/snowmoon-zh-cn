#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把「原始插图 | 中文插图」并排渲染成 PNG，供视觉复核。

用法: python3 pipeline/render_previews.py [插图名...]
产物: sources/work/previews/<name>.png
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "work" / "figures"
ZH = ROOT / "book" / "images"
OUT = ROOT / "sources" / "work" / "previews"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

HTML = """<html><head><meta charset="utf-8"><style>
body{{margin:0;background:#1b1b22;color:#ddd;font:13px -apple-system,"PingFang SC",sans-serif}}
.wrap{{display:flex;gap:10px;padding:10px;align-items:flex-start}}
.col{{flex:1 1 0;min-width:0}}
.cap{{padding:4px 2px;color:#9ab}}
img{{width:100%;height:auto;background:#000;border:1px solid #444;border-radius:6px}}
</style></head><body><div class="wrap">
<div class="col"><div class="cap">原文 {name}</div><img src="file://{src}"></div>
<div class="col"><div class="cap">中文版 {name}</div><img src="file://{zh}"></div>
</div></body></html>"""


def render(name: str) -> bool:
    svg = (SRC / f"{name}.svg").read_text(encoding="utf-8")
    h = float((re.search(r'height="([\d.]+)"', svg) or [0, 600])[1] or 600)
    w = float((re.search(r'width="([\d.]+)"', svg) or [0, 800])[1] or 800)
    win_h = max(320, min(1400, int(560 * h / max(w, 1)) + 90))
    html = HTML.format(name=name, src=SRC / f"{name}.svg", zh=ZH / f"{name}.svg")
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{name}.png"
    if png.exists():
        png.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        hp = Path(tmp) / "p.html"
        hp.write_text(html, encoding="utf-8")
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions",
               f"--user-data-dir={tmp}/prof", "--hide-scrollbars",
               f"--window-size=1200,{win_h}",
               f"--screenshot={png}", "--virtual-time-budget=2500",
               f"file://{hp}"]
        # Chrome 写完截图后不会自己退出（macOS 上会挂在 GPU 线程），
        # 所以这里边等文件边超时强杀。
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        deadline = time.time() + 40
        try:
            while time.time() < deadline:
                if png.exists() and png.stat().st_size > 0:
                    time.sleep(0.4)
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.25)
        finally:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
    return png.exists() and png.stat().st_size > 0


def main() -> None:
    names = sys.argv[1:] or sorted(p.stem for p in SRC.glob("*.svg"))
    ok = 0
    for n in names:
        good = render(n)
        ok += good
        print(("OK  " if good else "FAIL") + f" {n}", flush=True)
    print(f"{ok}/{len(names)} 张预览渲染成功 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
