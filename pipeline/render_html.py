#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""mini-markup → HTML 的公共渲染函数（供 build_site.py 使用）。

mini-markup 见 docs/style-guide.md：`<c st>` 上色、`<f>` 虚构语言字体、`<b>/<i>/<e>/<code>/<a>`
以及 `<sup>/<sub>/<u>/<small>/<mark>`；`<br/>` 为换行。

[用户请求] 中文不用斜体：`zh=True` 时 `<e>`/`<i>`（原文着重）渲染成 `<b>` 加粗，绝不输出 `<em>`；
英文栏 `zh=False` 保持斜体（英文排版本来就用斜体）。见 docs/style-guide.md §2。
"""
from __future__ import annotations

import html
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_markdown import oklch_to_hex  # noqa: E402

TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")


def mini_to_html(text: str, zh: bool = False) -> str:
    out: list[str] = []
    pos = 0
    links: list[str] = []
    for m in TAG_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        pos = m.end()
        closing, name, attrs, _ = m.groups()
        if name == "br":
            out.append("<br>")
        elif name == "c":
            sm = re.search(r'st="([^"]*)"', attrs)
            style = oklch_to_hex(sm.group(1)) if sm else ""
            if closing:
                out.append("</span>")
            else:
                out.append(f'<span style="{style}">' if style else "<span>")
        elif name == "f":
            out.append("</span>" if closing else '<span class="dz-script">')
        elif name == "b":
            out.append("</b>" if closing else "<b>")
        elif name in ("i", "e"):
            tag = "b" if zh else "em"
            out.append(f"</{tag}>" if closing else f"<{tag}>")
        elif name == "code":
            out.append("</code>" if closing else "<code>")
        elif name == "a":
            if closing:
                out.append(f'"{links.pop() if links else ""}">')
            else:
                hm = re.search(r'href="([^"]*)"', attrs)
                links.append(hm.group(1) if hm else "")
                out.append('<a href=')
        elif name in ("sup", "sub", "u", "small", "mark"):
            out.append(f"</{name}>" if closing else f"<{name}>")
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def expand(skeleton: str, segs: dict[str, str], zh: bool = False) -> str:
    return PLACEHOLDER_RE.sub(lambda m: mini_to_html(segs.get(m.group(1), ""), zh), skeleton)
