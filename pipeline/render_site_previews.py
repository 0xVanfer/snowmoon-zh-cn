#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把阅读站点在不同视口 / 设置下用 headless Chrome 截成 PNG，供人工与视觉模型复核。

做法：把 book/site 复制到临时目录，在正文页里插一段「预置 localStorage」的脚本，
这样可以在无头环境里指定主题、语言模式、翻页模式，而不必真的去点按钮。

用法:
    python3 pipeline/render_site_previews.py            # 全部预设视口
    python3 pipeline/render_site_previews.py wide home  # 只跑部分（id 见 PRESETS）
产物: sources/work/site-previews/<id>.png
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "book" / "site"
OUT = ROOT / "sources" / "work" / "site-previews"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PRESET_SCRIPT = """<script>
try{localStorage.setItem("snowmoon.reader.v1", JSON.stringify(%s));}catch(e){}
</script>
"""

# id: (页面相对路径, 视口宽, 视口高, localStorage 预设, 截图后额外等待毫秒)
PRESETS: dict[str, tuple] = {
    "home-wide":      ("index.html", 1440, 900, {"settings": {"theme": "paper"}}, 0),
    "home-narrow":    ("index.html", 390, 844, {"settings": {"theme": "paper"}}, 0),
    "toc-wide":       ("toc.html", 1440, 900, {"settings": {"theme": "paper"}, "last": 7}, 0),
    "toc-narrow":     ("toc.html", 390, 844, {"settings": {"theme": "paper"}, "last": 7}, 0),
    "read-wide-zh":   ("read/chapter-01.html", 1440, 900, {"settings": {"theme": "paper", "lang": "zh"}}, 300),
    "read-wide-dual": ("read/chapter-01.html", 1600, 900, {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    "read-wide-dark": ("read/chapter-07.html", 1280, 800, {"settings": {"theme": "dark", "lang": "zh"}}, 400),
    "read-wide-paged": ("read/chapter-01.html", 1440, 900,
                        {"settings": {"theme": "paper", "lang": "zh", "mode": "paged"}}, 500),
    "read-narrow-zh": ("read/chapter-01.html", 390, 844, {"settings": {"theme": "paper", "lang": "zh"}}, 300),
    "read-narrow-dual": ("read/chapter-01.html", 390, 844,
                         {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    "read-tablet-dual": ("read/chapter-01.html", 820, 1180,
                         {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    "vote-row":       ("read/chapter-01.html", 900, 2300, {"settings": {"theme": "light", "lang": "zh"}}, 300),
    "emoji-row":      ("read/chapter-07.html", 1000, 800, {"settings": {"theme": "light", "lang": "zh"}}, 300),
    "read-longwide":  ("read/chapter-01.html", 2200, 780,
                       {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    # 交互态（探针会按 probe_site.ACTIONS 先点击再测量）
    "read-narrow-tab-en": ("read/chapter-01.html", 390, 844,
                           {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    "read-wide-paged-next": ("read/chapter-01.html", 1440, 900,
                             {"settings": {"theme": "paper", "lang": "zh", "mode": "paged"}}, 500),
    "read-wide-settings": ("read/chapter-01.html", 1440, 900,
                           {"settings": {"theme": "paper", "lang": "dual"}}, 400),
    "read-scroll-next": ("read/chapter-01.html", 1440, 900,
                         {"settings": {"theme": "paper", "lang": "zh", "mode": "scroll"}}, 400),
    "read-paged-figures": ("read/chapter-04.html", 1440, 900,
                           {"settings": {"theme": "paper", "lang": "zh", "mode": "paged"}}, 500),
    "read-sync-scroll": ("read/chapter-01.html", 1600, 900,
                         {"settings": {"theme": "paper", "lang": "dual", "sync": True}}, 400),
    "read-keyboard": ("read/chapter-01.html", 1440, 900,
                      {"settings": {"theme": "paper", "lang": "zh"}}, 400),
    "read-clickzone": ("read/chapter-01.html", 1000, 800,
                       {"settings": {"theme": "paper", "lang": "zh"}}, 400),
    "read-progress-save": ("read/chapter-01.html", 1000, 800,
                           {"settings": {"theme": "paper", "lang": "zh"}}, 400),
    "read-bottom": ("read/chapter-01.html", 1440, 900,
                    {"settings": {"theme": "paper", "lang": "zh"}}, 400),
}


# 需要按手机尺寸渲染的预设：Chrome headless 在 macOS 上最小窗口宽约 500px，
# 直接开 390px 的窗口会被裁掉右边；这里改用「手机框 iframe」——iframe 里是独立的 CSS 视口，
# 媒体查询/容器查询都按框宽生效。
FRAMED = {
    "home-narrow": (390, 844),
    "toc-narrow": (390, 844),
    "read-narrow-zh": (390, 844),
    "read-narrow-dual": (390, 844),
    "read-narrow-tab-en": (390, 844),
}

FRAME_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#20242b}
.phone{width:%dpx;height:%dpx;margin:20px auto;border:10px solid #11141a;border-radius:22px;
       overflow:hidden;background:#fff}
iframe{width:100%%;height:100%%;border:0;display:block}
</style></head><body><div class="phone"><iframe src="%s"></iframe></div></body></html>
"""


def window_args(w: int, h: int) -> list[str]:
    """Chrome headless 在 macOS 上有约 500px 的最小窗口宽，窄屏直接给 390 会被裁掉右边；
    这里把窗口开在 500px、用 device-scale-factor 把 CSS 视口缩到目标宽度。"""
    minimum = 500
    if w < minimum:
        return [f"--window-size={minimum},{h}", f"--force-device-scale-factor={minimum / w:.5f}"]
    return [f"--window-size={w},{h}"]


# 交互态截图/探针需要先「点一下再拍」：pid -> 在 load 之后执行的 JS
ACTIONS = {
    "read-narrow-tab-en": "document.querySelector('#tab-en').click();",
    "read-wide-paged-next": ("document.querySelector('#btn-next-screen').click();"
                             "document.querySelector('#btn-next-screen').click();"),
    "read-wide-settings": "document.getElementById('btn-settings').click();",
    "read-scroll-next": "document.querySelector('#btn-next-screen').click();",
    # 反复滚几次：分栏判定是异步的，第一次滚动可能还没进入「分栏 + 同步」状态
    "read-sync-scroll": ("var n=0,iv=setInterval(function(){var z=document.getElementById('pane-zh');"
                         "z.scrollTop=Math.round((z.scrollHeight-z.clientHeight)*0.5);"
                         "if(++n>6)clearInterval(iv);},300);"),
    "read-keyboard": "document.dispatchEvent(new KeyboardEvent('keydown',{key:'t',bubbles:true}));",
    "read-clickzone": ("var p=document.getElementById('pane-zh'), r=p.getBoundingClientRect();"
                       "p.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1,"
                       "clientX:r.left+r.width*0.85,clientY:r.top+120}));"),
    # 连续滚几次：站点要等正文准备完（ready）后才记录进度，单次滚动可能发生在 ready 之前
    "read-progress-save": ("var n=0,iv=setInterval(function(){window.scrollTo(0,2200);"
                           "if(++n>20)clearInterval(iv);},200);"),
    "read-bottom": ("var n=0,iv=setInterval(function(){window.scrollTo(0,"
                    "document.documentElement.scrollHeight);if(++n>6)clearInterval(iv);},300);"),
}

ACTION_SCRIPT = ('<script id="preset-action">window.addEventListener("load",function(){'
                 'setTimeout(function(){try{%s}catch(e){}},%d);});</script>\n')


def stage(tmp: Path, rel: str, preset: dict | None, pid: str = "") -> Path:
    """把站点复制出来，并在目标页 reader.js 之前插入 localStorage 预置脚本。"""
    dst = tmp / "site"
    if not dst.exists():
        shutil.copytree(SITE, dst)
    page = dst / rel
    if preset is not None:
        raw = page.read_text(encoding="utf-8")
        state = {"v": 1, "last": 1, "settings": {}, "chapters": {}}
        state.update({k: v for k, v in preset.items() if k != "settings"})
        state["settings"].update(preset.get("settings", {}))
        # 只覆盖页面自己声明的默认值，字体/字号等其余设置交给站点默认值
        inject = ('<script id="preset-inject">try{localStorage.setItem("snowmoon.reader.v1",'
                  'JSON.stringify(%s));}catch(e){}</script>\n' % json.dumps(state, ensure_ascii=False))
        # 同一个临时目录里会被反复 stage，先清掉上一次注入，保证幂等
        raw = re.sub(r'<script id="preset-inject">.*?</script>\n?', '', raw, flags=re.S)
        raw = raw.replace('<script src="', inject + '<script src="', 1)
        action = ACTIONS.get(pid)
        raw = re.sub(r'<script id="preset-action">.*?</script>\n?', '', raw, flags=re.S)
        if action:
            raw = raw.replace("</head>", ACTION_SCRIPT % (action, 600) + "</head>", 1)
        page.write_text(raw, encoding="utf-8")
    return page


def shoot(page: Path, png: Path, w: int, h: int, wait_ms: int) -> bool:
    png.parent.mkdir(parents=True, exist_ok=True)
    if png.exists():
        png.unlink()
    with tempfile.TemporaryDirectory() as prof:
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
               f"--user-data-dir={prof}", *window_args(w, h),
               f"--screenshot={png}", f"--virtual-time-budget={2500 + wait_ms}",
               f"file://{page}"]
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


# headless 的 --screenshot 拍「滚动后的页面」会出空白图，所以滚动类的预设只跑探针、不截图
SKIP_SHOTS = {"read-scroll-next", "read-clickzone", "read-progress-save", "read-bottom",
              "read-sync-scroll"}


def main() -> None:
    want = sys.argv[1:]
    todo = {k: v for k, v in PRESETS.items()
            if (not want or k in want) and k not in SKIP_SHOTS}
    ok = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for pid, (rel, w, h, preset, wait) in todo.items():
            page = stage(tmp, rel, preset, pid)
            png = OUT / f"{pid}.png"
            if pid in FRAMED:
                fw, fh = FRAMED[pid]
                frame = tmp / "site" / "_frame.html"
                frame.write_text(FRAME_HTML % (fw, fh, rel), encoding="utf-8")
                good = shoot(frame, png, 500, fh + 60, wait)
            else:
                good = shoot(page, png, w, h, wait)
            ok += good
            print(("OK  " if good else "FAIL") + f" {pid:<18} {rel} {w}x{h}", flush=True)
    print(f"截图 {ok}/{len(todo)} → sources/work/site-previews/")


if __name__ == "__main__":
    main()
