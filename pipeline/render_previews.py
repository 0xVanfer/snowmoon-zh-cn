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

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Chrome 的定位与「本机真能渲染」的验证在 chrome_runtime 一处，与 render_site_previews 共用。
from chrome_runtime import CHROME, CHROME_EXTRA, can_screenshot, flags_for  # noqa: E402

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
    root = (re.search(r"<svg\b[^>]*>", svg, re.I) or re.match(r"", "")).group(0)
    h = float((re.search(r'height="([\d.]+)"', root) or [0, 600])[1] or 600)
    w = float((re.search(r'width="([\d.]+)"', root) or [0, 800])[1] or 800)
    win_h = max(320, min(1400, int(560 * h / max(w, 1)) + 90))
    html = HTML.format(name=name, src=SRC / f"{name}.svg", zh=ZH / f"{name}.svg")
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{name}.png"
    if png.exists():
        png.unlink()
    with tempfile.TemporaryDirectory() as tmp:
        hp = Path(tmp) / "p.html"
        hp.write_text(html, encoding="utf-8")
        cmd = [CHROME, *flags_for(CHROME, CHROME_EXTRA),
               f"--user-data-dir={tmp}/prof",
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
    if not names:
        raise SystemExit("没有可渲染的插图（sources/work/figures 为空？）")
    # 先问「这台机器拍不拍得出图」：本机没有可用显示链路时，挨个插图各打一行 FAIL，
    # 看起来像插图全坏了，实际一张都没渲染过（见 docs/lessons.md 第 10 节）。
    can, why = can_screenshot()
    if not can:
        print(f"本机拍不了截图，已跳过 {len(names)} 张。原因：{why}")
        print("这是环境限制（headless 浏览器没有可用的显示链路），不是插图有问题。")
        sys.exit(1)
    ok = 0
    for n in names:
        good = render(n)
        ok += good
        print(("OK  " if good else "FAIL") + f" {n}", flush=True)
    print(f"{ok}/{len(names)} 张预览渲染成功 → {OUT.relative_to(ROOT)}")
    # 渲染失败必须反映到退出码，否则「0/N 成功」也会被当成通过
    sys.exit(1 if ok != len(names) else 0)


if __name__ == "__main__":
    main()
