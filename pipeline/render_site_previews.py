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
import shlex
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


def chrome_path() -> str:
    """定位 Chrome：环境变量 CHROME 优先，其次 macOS 默认位置、常见替代路径，
    最后是 Playwright 缓存里的 headless_shell（见 chrome_flags 的说明）。"""
    env = os.environ.get("CHROME") or os.environ.get("CHROME_PATH")
    if env:
        return env
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return found
    # Playwright 下载的 headless shell 是独立二进制，自带 headless 模式，
    # 不依赖系统装了 Chrome。版本号会随 Playwright 升级变化，所以用通配。
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    for pattern in ("chromium_headless_shell-*/chrome-mac/headless_shell",
                     "chromium_headless_shell-*/chrome-mac/chrome-headless-shell",
                     "chromium_headless_shell-*/chrome-linux/headless_shell"):
        hits = sorted(cache.glob(pattern), reverse=True)
        if hits:
            return str(hits[0])
    raise SystemExit("找不到 Chrome：请设置环境变量 CHROME=<可执行文件路径>（headless 渲染需要它）")

CHROME = chrome_path()


def is_headless_shell(path: str) -> bool:
    """Playwright 的 headless_shell 是独立二进制，自带 headless 模式。

    对它再传 `--headless=new` 会被当成未知开关，行为也不受支持。
    """
    return "headless_shell" in Path(path).name or "headless-shell" in Path(path).name


def chrome_flags() -> list[str]:
    """所有 Chrome 调用的公共 flag（截图与几何探针共用，免得两处各写一份跑偏）。

    某些受限沙箱禁止进程向 Mach bootstrap 注册服务，Chrome 会在
    `mach_port_rendezvous_mac.cc` / `base/mac/mac_util.mm` 直接 FATAL 退出（exit 133，
    `bootstrap_check_in ...: Permission denied (1100)`）。`--single-process` 不走
    zygote 与 rendezvous，实测可以绕开。但单进程模式本身不够稳，不该无条件打开——
    因此只从环境变量 `CHROME_EXTRA_ARGS` 追加，默认什么都不加。
    """
    flags = [] if is_headless_shell(CHROME) else ["--headless=new"]
    flags += ["--disable-gpu", "--no-sandbox", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars"]
    flags += shlex.split(os.environ.get("CHROME_EXTRA_ARGS", ""))
    return flags


# id: (页面相对路径, 视口宽, 视口高, localStorage 预设, 截图后额外等待毫秒)
PRESETS: dict[str, tuple] = {
    "home-wide":      ("index.html", 1440, 900, {"settings": {"theme": "paper"}}, 0),
    "home-narrow":    ("index.html", 390, 844, {"settings": {"theme": "paper"}}, 0),
    "toc-wide":       ("toc.html", 1440, 900,
                       {"settings": {"theme": "paper"}, "last": 7,
                        "chapters": {"1": {"read": True}}}, 0),
    "toc-narrow":     ("toc.html", 390, 844,
                       {"settings": {"theme": "paper"}, "last": 7,
                        "chapters": {"1": {"read": True}}}, 0),
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
    # §3.2 回归：双语标签页切到英文栏（该栏从未分列过）后按「下一屏」。
    # 若 api.step 取消 rAF 后不补排版，英文栏 m.pages 还是初值 1，
    # next>=pages 恒真 → 读者被直接踢到下一章；paged 视口又是 overflow:hidden，
    # 没排版的栏既翻不动也滚不动，卡死。
    "read-paged-tab-next": ("read/chapter-01.html", 390, 844,
                            {"settings": {"theme": "paper", "lang": "dual", "mode": "paged"}}, 500),
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
    # 「一句一行」中文段式
    "read-webnovel-zh": ("read/chapter-01.html", 1440, 900,
                         {"settings": {"theme": "paper", "lang": "zh", "paragraph": "webnovel"}}, 400),
    # 末章：底栏「下一章」应隐藏、「上一章」指向第 31 章
    "read-last-chapter": ("read/chapter-32.html", 1440, 900,
                          {"settings": {"theme": "paper", "lang": "zh"}}, 400),
    # 滚轮接管：内层滚动区先滚自己、到边接续整页、整页到底再滚正文栏
    "read-wheel-chain": ("read/chapter-01.html", 1600, 900,
                         {"settings": {"theme": "paper", "lang": "dual", "sync": True}}, 400),
    # 先窄后宽（手机框 390 → 拉宽到 1600）：验证能从标签页恢复分栏
    "read-dual-recover": ("read/chapter-01.html", 390, 844,
                          {"settings": {"theme": "paper", "lang": "dual"}}, 400),
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
    "read-dual-recover": (390, 844),
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
    # 切栏与按「下一屏」必须在**同一个 tick** 内完成，中间不能等：
    # 切栏会经 MutationObserver 排一次异步 layout，等它跑完英文栏就已经分列好了，
    # api.step 里那个「当前栏还没排版」的分支根本走不到。
    # 真实读者在标签页上连点两下的手势正是这样——两个事件落在同一帧里。
    "read-paged-tab-next": (
        "document.querySelector('#tab-en').click();"
        "var b=document.getElementById('btn-next-screen');if(b)b.click();"),
    # 反复滚几次：分栏判定是异步的，第一次滚动可能还没进入「分栏 + 同步」状态。
    # 另需手动补一次 scroll 事件：无头 + --virtual-time-budget 下，嵌套滚动容器（正文栏）
    # 的 scroll 事件经常排进队列却轮不到一次渲染帧去派发，探针会误判成「同步滚动没生效」。
    # 派发事件测的是页面「收到栏内滚动后应如何响应」，浏览器自身是否派发不在被测范围内。
    "read-sync-scroll": ("var n=0,iv=setInterval(function(){var z=document.getElementById('pane-zh');"
                         "z.scrollTop=Math.round((z.scrollHeight-z.clientHeight)*0.5);"
                         "z.dispatchEvent(new Event('scroll'));"
                         "if(++n>6)clearInterval(iv);},300);"),
    "read-keyboard": "document.dispatchEvent(new KeyboardEvent('keydown',{key:'t',bubbles:true}));",
    "read-clickzone": ("var p=document.getElementById('pane-zh'), r=p.getBoundingClientRect();"
                       "p.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1,"
                       "clientX:r.left+r.width*0.85,clientY:r.top+120}));"),
    # 连续滚几次：站点要等正文准备完（ready，relayout 跑完才会写进度条宽度）之后才记录进度，
    # 先滚动的事件会被丢弃。这里先等进度条出现宽度再滚；与 read-sync-scroll 同理，
    # 无头 + 虚拟时间下滚动事件偶发派发不到，补派发一次（测的是页面「收到滚动后如何记录进度」）。
    "read-progress-save": ("var n=0,idle=0,iv=setInterval(function(){"
                           "var bar=document.getElementById('progress-bar');"
                           "if(!bar||!bar.style.width){if(++idle>16)clearInterval(iv);return;}"
                           "window.scrollTo(0,2200);document.dispatchEvent(new Event('scroll'));"
                           "if(++n>8)clearInterval(iv);},250);"),
    "read-bottom": ("var n=0,iv=setInterval(function(){window.scrollTo(0,"
                    "document.documentElement.scrollHeight);if(++n>6)clearInterval(iv);},300);"),
    # 滚轮接管：在正文里临时插一个可滚动区块，用合成的 wheel 事件走三条分支
    # （内层有余量 / 内层到边 + 整页在顶部 / 整页到底）
    "read-wheel-chain": (
        "window.__wheel={};"
        "var content=document.querySelector('#pane-zh .chapter-content');"
        "var host=document.createElement('div');"
        "host.id='wheel-test';"
        "host.style.cssText='height:120px;overflow-y:auto;margin:8px 0;border:1px solid #ccc';"
        "host.innerHTML='<div style=\"height:1400px\">inner</div>';"
        "content.insertBefore(host,content.firstChild);"
        "var pane=document.getElementById('pane-zh');"
        "var doc=document.scrollingElement||document.documentElement;"
        "function wheel(el,dy){var e=new WheelEvent('wheel',{deltaY:dy,bubbles:true,cancelable:true});"
        "el.dispatchEvent(e);return e;}"
        "host.scrollTop=100;"
        "var ev1=wheel(host,200);"
        "window.__wheel.innerPrevented=ev1.defaultPrevented;"
        "window.__wheel.innerPaneDelta=pane.scrollTop;"
        "window.__wheel.innerDocDelta=doc.scrollTop;"
        "host.scrollTop=host.scrollHeight-host.clientHeight;"
        "doc.scrollTop=0;pane.scrollTop=0;"
        "wheel(host,400);"
        "window.__wheel.edgeDocDelta=doc.scrollTop;"
        "window.__wheel.edgePaneDelta=pane.scrollTop;"
        "doc.scrollTop=doc.scrollHeight-doc.clientHeight;pane.scrollTop=0;"
        "wheel(host,200);"
        "window.__wheel.deepPaneDelta=pane.scrollTop;"
        "window.__wheel.headingTop=Math.round("
        "document.querySelector('.chapter-heading').getBoundingClientRect().top);"),
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
        if '<script src="' in raw:
            raw = raw.replace('<script src="', inject + '<script src="', 1)
        elif "</head>" in raw:
            raw = raw.replace("</head>", inject + "</head>", 1)
        else:
            raise SystemExit(f"{rel}: 页面里既没有 <script src=> 也没有 </head>，无法注入预设")
        action = ACTIONS.get(pid)
        raw = re.sub(r'<script id="preset-action">.*?</script>\n?', '', raw, flags=re.S)
        if action:
            if "</head>" not in raw:
                raise SystemExit(f"{rel}: 页面缺少 </head>，无法注入动作脚本")
            raw = raw.replace("</head>", ACTION_SCRIPT % (action, 600) + "</head>", 1)
        page.write_text(raw, encoding="utf-8")
    return page


def shoot(page: Path, png: Path, w: int, h: int, wait_ms: int) -> bool:
    png.parent.mkdir(parents=True, exist_ok=True)
    if png.exists():
        png.unlink()
    with tempfile.TemporaryDirectory() as prof:
        cmd = [CHROME, *chrome_flags(),
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
              "read-sync-scroll", "read-wheel-chain"}


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
    if not todo:
        raise SystemExit("没有匹配的预设")
    print(f"截图 {ok}/{len(todo)} → sources/work/site-previews/")
    sys.exit(1 if ok != len(todo) else 0)


if __name__ == "__main__":
    main()
