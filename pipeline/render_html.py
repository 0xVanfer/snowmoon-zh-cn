#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""mini-markup → HTML 的公共渲染函数（供 build_site.py 使用）。

mini-markup 见 docs/style-guide.md：`<c st>` 上色、`<f>` 虚构语言字体、`<b>/<i>/<e>/<code>/<a>`
以及 `<sup>/<sub>/<u>/<small>/<mark>`；`<br/>` 为换行。

两点易错之处，改这里时必须留意：
  * 片段文本在抽取阶段就做过 HTML 实体转义（`&`→`&amp;` 等），因此这里**不能**再整体
    `html.escape` 一遍，否则 `&gt;` 会变成 `&amp;gt;` 并在页面上显示成字面量。
    这里只补转义游离的 `&` 与意外的 `<`、`>`。
  * `<a>` 必须渲染成 `<a href="URL">文字</a>`：URL 属于开始标签，文字在标签之间。

[用户请求] 中文不用斜体：`zh=True` 时 `<e>`/`<i>`（原文着重）渲染成 `<b>` 加粗，绝不输出 `<em>`；
英文栏 `zh=False` 保持斜体（英文排版本来就用斜体）。见 docs/style-guide.md §2。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_markdown import oklch_to_hex  # noqa: E402

TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")
# 游离的 &（不是合法实体的一部分）才需要转义
BARE_AMP_RE = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});)")
KNOWN_TAGS = {"br", "c", "f", "b", "i", "e", "code", "a", "sup", "sub", "u", "small", "mark"}


def esc_visible(s: str) -> str:
    """转义「尚未转义」的字符，但不碰已有实体（片段文本抽取时已转义过一轮）。"""
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return BARE_AMP_RE.sub("&amp;", s)


def mini_to_html(text: str, zh: bool = False) -> str:
    out: list[str] = []
    pos = 0
    links: list[str] = []
    for m in TAG_RE.finditer(text):
        out.append(esc_visible(text[pos:m.start()]))
        pos = m.end()
        closing, name, attrs, _ = m.groups()
        if name not in KNOWN_TAGS:
            raise SystemExit(
                f"mini-markup 出现非法标签 <{name}>（片段只允许 "
                f"{', '.join(sorted(KNOWN_TAGS))}）: {text[:80]!r}")
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
                links.pop() if links else None
                out.append("</a>")
            else:
                hm = re.search(r'href="([^"]*)"', attrs)
                url = hm.group(1) if hm else ""
                links.append(url)
                out.append(f'<a href="{url}">')
        elif name in ("sup", "sub", "u", "small", "mark"):
            out.append(f"</{name}>" if closing else f"<{name}>")
    out.append(esc_visible(text[pos:]))
    return "".join(out)


def expand(skeleton: str, segs: dict[str, str], zh: bool = False) -> str:
    """把骨架里的 {{S:id}} 换成渲染后的正文。

    片段缺失时**直接报错**：这是全流水线唯一把结构与文字汇合的地方，
    静默替换成空串会让整段正文凭空消失而没有任何人发现。
    """
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in segs:
            raise SystemExit(f"骨架引用了不存在的片段 {key}（译文与骨架不同步）")
        return mini_to_html(segs[key], zh)

    return PLACEHOLDER_RE.sub(sub, skeleton)
