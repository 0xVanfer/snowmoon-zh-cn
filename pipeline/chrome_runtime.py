#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""定位并验证一个**在本机真能渲染**的 headless Chrome。

`render_site_previews.py`（阅读站点截图 / 几何探针）与 `render_previews.py`（插图对照）
都需要 Chrome。两者曾经各写一份 `chrome_path()`，而那份实现只判断**文件存不存在**——
在受限沙箱里系统 Chrome 常常存在却根本跑不起来（启动阶段 FATAL 退出），
于是整套探针一路 0 字节，最后报成几十条「断言失败」。环境问题和真实回归在报告里
长得一模一样，等于没有信号。这里把「挑 Chrome」收成一处，并且**必须真跑一次**。

用法:
    from chrome_runtime import CHROME, CHROME_EXTRA, flags_for
    cmd = [CHROME, *flags_for(CHROME, CHROME_EXTRA), ...]
"""
from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def is_headless_shell(path: str) -> bool:
    """Playwright 的 headless_shell 是独立二进制，自带 headless 模式。

    对它再传 `--headless=new` 会被当成未知开关，行为也不受支持。
    """
    return "headless_shell" in Path(path).name or "headless-shell" in Path(path).name


def flags_for(path: str, extra: list[str] | None = None) -> list[str]:
    """某个 Chrome 可执行文件该配哪些 flag。

    某些受限沙箱禁止进程向 Mach bootstrap 注册服务，Chrome 会在
    `mach_port_rendezvous_mac.cc` / `base/mac/mac_util.mm` 直接 FATAL 退出（exit 133，
    `bootstrap_check_in ...: Permission denied (1100)`）。`--single-process` 不走
    zygote 与 rendezvous，实测可以绕开。但单进程模式本身不够稳，不该无条件打开——
    所以只对**烟测确认过需要**的那个二进制加，别的照常用默认多进程模式。
    用户还可以用 `CHROME_EXTRA_ARGS` 追加，它排在最后、优先级最高。
    """
    flags = [] if is_headless_shell(path) else ["--headless=new"]
    flags += ["--disable-gpu", "--no-sandbox", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars"]
    flags += list(extra or [])
    flags += shlex.split(os.environ.get("CHROME_EXTRA_ARGS", ""))
    return flags


def candidates() -> list[str]:
    """按优先级列出 Chrome 可执行文件候选（**只判断文件在不在**）。

    真正的挑选在 `resolve()`：那里每个候选都要真跑一次烟测。
    """
    out: list[str] = []
    env = os.environ.get("CHROME") or os.environ.get("CHROME_PATH")
    if env:
        out.append(env)
    out += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ]
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        out.append(found)
    # Playwright 下载的 headless shell 是独立二进制，自带 headless 模式，
    # 不依赖系统装了 Chrome。版本号会随 Playwright 升级变化，所以用通配。
    cache = Path.home() / "Library" / "Caches" / "ms-playwright"
    for pattern in ("chromium_headless_shell-*/chrome-mac/headless_shell",
                    "chromium_headless_shell-*/chrome-mac/chrome-headless-shell",
                    "chromium_headless_shell-*/chrome-linux/headless_shell"):
        out += [str(h) for h in sorted(cache.glob(pattern), reverse=True)]
    seen, uniq = set(), []
    for c in out:
        if c not in seen and Path(c).exists():
            seen.add(c)
            uniq.append(c)
    return uniq


def smoke(path: str, extra: list[str] | None = None) -> tuple[bool, str]:
    """真跑一次 `--dump-dom`，看这个二进制在本机能不能真的渲染出 DOM。

    返回 (能不能用, 失败时的最后一行 stderr)。判定标准是输出里出现标记文本——
    只看退出码不行：受限沙箱里 Chrome 在启动阶段 FATAL，而 `--dump-dom`
    的 stdout 在那之前一直是空的。
    """
    mark = "SNOWMOON-CHROME-SMOKE"
    with tempfile.TemporaryDirectory() as td:
        dom_p, err_p = Path(td) / "dom.html", Path(td) / "err.txt"
        cmd = [path, *flags_for(path, extra), f"--user-data-dir={td}/p",
               "--virtual-time-budget=2000", "--dump-dom",
               f"data:text/html,<b>{mark}</b>"]
        with dom_p.open("wb") as out, err_p.open("wb") as err:
            proc = subprocess.Popen(cmd, stdout=out, stderr=err, start_new_session=True)
            deadline = time.time() + 30
            try:
                while time.time() < deadline:
                    if dom_p.exists() and mark.encode() in dom_p.read_bytes()[-65536:]:
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)
            finally:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        ok = dom_p.exists() and mark.encode() in dom_p.read_bytes()
        lines = err_p.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        return ok, (lines[-1][:200] if lines else "")


def resolve() -> tuple[str, list[str]]:
    """挑一个**在本机真能渲染**的 Chrome，返回 (可执行文件, 额外的 flag)。

    候选依次试，每个候选先按默认 flag 试，再试 `--single-process`；第一个能出 DOM 的
    即采用。这样受限沙箱里会自动退到 Playwright 的 headless_shell + 单进程模式
    （lessons.md §10 记的那个绕法），而不是让整套探针一路 FATAL 却报成「断言失败」。

    一个候选都跑不通时直接 `SystemExit`：**环境问题必须当场死在导入期、说清原因**，
    绝不能让它伪装成几十条断言失败混进报告里。
    """
    tried: list[str] = []
    for path in candidates():
        for extra in ([], ["--single-process"]):
            ok, why = smoke(path, extra)
            if ok:
                return path, extra
            tried.append(f"  {Path(path).name}{' ' + ' '.join(extra) if extra else ''}: "
                         f"{why or '没输出 DOM'}")
    raise SystemExit(
        "找不到能在本机跑起来的 Chrome（headless 渲染需要它）。\n"
        + "\n".join(tried)
        + "\n受限沙箱里 Chrome 常见 `bootstrap_check_in ... Permission denied (1100)` → "
          "`mac_util.mm` FATAL；装一下 Playwright 的 headless_shell 可解，"
          "或用环境变量 CHROME=<可执行文件路径> 指定。")


CHROME, CHROME_EXTRA = resolve()

_shot_cache: tuple[bool, str] | None = None


def can_screenshot() -> tuple[bool, str]:
    """这个 Chrome 能不能真的截图。返回 (能不能, 不能时的原因)。**结果只算一次。**

    「起得来」不等于「拍得出」：某些受限沙箱里 headless shell 能跑 `--dump-dom`，
    却没有可用的显示链路（`CVDisplayLinkCreateWithCGDisplay failed`），
    `--screenshot` 会**正常退出、返回 0，却只写出 0 字节的 PNG**。
    所以判据是产物存在且非空，不是退出码。

    截图链路（render_site_previews / render_previews）先问这一句，
    把「本机拍不了图」和「页面渲染坏了」分开报——两者在输出里曾经长得一模一样。
    """
    global _shot_cache
    if _shot_cache is not None:
        return _shot_cache
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "shot.png"
        cmd = [CHROME, *flags_for(CHROME, CHROME_EXTRA), f"--user-data-dir={td}/p",
               "--window-size=800,600", f"--screenshot={png}",
               "--virtual-time-budget=1500", "data:text/html,<b>SHOT</b>"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40,
                                  errors="replace")
        except subprocess.TimeoutExpired:
            _shot_cache = (False, "截图命令 40 秒没退出（无显示链路时单进程模式会挂住）")
            return _shot_cache
        except OSError as e:
            _shot_cache = (False, f"起不来：{e}")
            return _shot_cache
        size = png.stat().st_size if png.exists() else 0
        if size > 0:
            _shot_cache = (True, "")
            return _shot_cache
        why = ""
        for line in (proc.stderr or "").strip().splitlines():
            if "ERROR" in line or "FATAL" in line:
                why = line.split(":", 2)[-1].strip()[:120]
                break
        _shot_cache = (False, why or f"只写出 0 字节的 PNG（退出码 {proc.returncode}）")
        return _shot_cache
