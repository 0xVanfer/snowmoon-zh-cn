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

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_markdown import oklch_to_hex  # noqa: E402
from terms import TIER_LABEL, WEIGHT_LABEL, page_url  # noqa: E402

TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")
# 游离的 &（不是合法实体的一部分）才需要转义
BARE_AMP_RE = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]{1,31}|#\d{1,7}|#[xX][0-9A-Fa-f]{1,6});)")
# <tn note="cNN-sNNNN">…</tn>：被译者注解释的词。译文专用，英文栏不出现。
KNOWN_TAGS = {"br", "c", "f", "b", "i", "e", "code", "a", "sup", "sub", "u", "small", "mark", "tn"}
# <a> 之外唯一带 href/note 之类的标签，其属性值需转义
ATTR_VALUE_RE = re.compile(r'(note|href)="([^"]*)"')

# 译注气泡的容器类名（build_site 与 style/reader 共用同一约定）
TNOTE_CLASS = "tnote"
TNOTE_STORE_CLASS = "tnote-store"

# 术语卡片的约定类名（与 .tnote-store 同理，容器零布局）
TERM_CLASS = "term"
TERM_STORE_CLASS = "term-store"
TERM_CARD_CLASS = "term-card"

# 块级锚点：<p id="c22-s0152">。docs/explainer 的 `chapter-NN.md:行号` 引用
# 靠 build_markdown 产出的行号索引换算到这里，读者点章号 chip 能落到具体那一段。
FIRST_TAG_RE = re.compile(r"^(\s*<[a-zA-Z][a-zA-Z0-9-]*)")
HAS_ID_RE = re.compile(r"^(\s*<[a-zA-Z][a-zA-Z0-9-]*)[^>]*\bid=")


def inject_anchor(fragment: str, seg_id: str | None) -> str:
    """给一块产物的**首个标签**加上 id，用于深链定位。

    只处理首个标签、只加属性不改结构：章节页的布局校验会逐项比对正文与骨架的
    容器子项，任何新增包裹元素都会让「布局容器子项与原文逐项一致」报警。
    首个标签不是标签（纯文本块）或已有 id 时原样返回——由 validate_terms.py 兜底报错。
    """
    if not seg_id or not fragment:
        return fragment
    if HAS_ID_RE.match(fragment):
        return fragment
    m = FIRST_TAG_RE.match(fragment)
    if not m:
        return fragment
    return f'{m.group(1)} id="{html.escape(seg_id, quote=True)}"' + fragment[m.end():]


def term_cards(concepts: list[dict], prereq_index: dict[str, dict] | None = None) -> str:
    """术语卡片池。结构与 tnote_bubbles 完全一致：正文只留触发点，内容集中挂一次。

    [坑] 容器**不能**加 `hidden` 或任何 display:none —— display:none 会连后代一起
    隐藏，后代无法覆盖祖先，于是 JS 把 card.hidden 置回 false 也照样看不见
    （与 .tnote-store 同一个坑，见 tnote_bubbles 的说明）。靠 `display: contents`
    做到零布局，显示/隐藏完全交给每张卡自己的 hidden。

    [只讲最基础概念] 气泡里**不放**「这个概念在后面哪些章出现、各自什么作用」——
    那是前后文关系。读者在正文里只需要知道「这个词是什么意思」，剩下的交给完整教程页。
    早先版本把章号列表放进了气泡，一张卡能到二十多行：手机屏放不下，而**卡内滚动在触屏上
    并不可靠**（指针从词移向卡就会触发 mouseleave 收卡），于是读者看到的是「下半截被截断、
    也划不动」。现在改成**从结构上保证装得下**：固定 4 段（概念名 / 定义 / 比喻 / 链接），
    「先读」最多再占 1 行，单行长度上限由 validate_terms.py 按最窄视口 + 最大字号断言。

    概念在哪些章出现这份数据仍然由 `terms.ref_anchors()` 算出，校验器拿它对账文档里的
    引用有没有漂移——只是不再渲染进气泡。
    """
    if not concepts:
        return ""
    prereq_index = prereq_index or {}
    rows = []
    for c in concepts:
        pre = []
        for pid in c.get("prereq") or []:
            p = prereq_index.get(pid)
            if p:
                pre.append(f'<a href="{html.escape(page_url(p["doc"]), quote=True)}"'
                           f' target="_blank" rel="noopener">{html.escape(p["zh"])}</a>')
        prereq_html = (f'<p class="{TERM_CARD_CLASS}__prereq">先读：{"、".join(pre)}</p>'
                       if pre else '')
        card = c.get("card") or {}
        rows.append(
            f'<div class="{TERM_CARD_CLASS}" id="tc-{html.escape(c["id"], quote=True)}" hidden>'
            f'<p class="{TERM_CARD_CLASS}__head">'
            f'<span class="{TERM_CARD_CLASS}__name">{html.escape(c.get("zh", ""))}</span>'
            f'<span class="{TERM_CARD_CLASS}__tier term-card__tier--{c.get("tier")}">'
            f'{html.escape(TIER_LABEL.get(c.get("tier"), ""))}</span>'
            f'</p>'
            f'<p class="{TERM_CARD_CLASS}__line">{html.escape(card.get("one_liner", ""))}</p>'
            f'<p class="{TERM_CARD_CLASS}__analogy">{html.escape(card.get("analogy", ""))}</p>'
            + prereq_html
            + f'<a class="{TERM_CARD_CLASS}__more" href="{html.escape(page_url(c["doc"]), quote=True)}"'
              f' target="_blank" rel="noopener">读完整教程 ↗</a>'
            + '</div>')
    return f'<div class="{TERM_STORE_CLASS}">{"".join(rows)}</div>'

def tnote_bubbles(notes: dict[str, str]) -> str:
    """把一章的译者注渲染成章尾的气泡池。

    气泡不放在正文流里：正文只留触发点，注的内容集中挂一次，
    既避免同一段里多个注互相挤位，也方便日后批量增删注。

    [坑] 容器**不能**加 `hidden`（或任何 display:none）。`display:none` 会连
    所有后代一起隐藏，后代无法覆盖祖先 —— 于是 reader.js 把 bubble.hidden 置回
    false 也照样看不见。容器靠 `.tnote-store { display: contents }` 做到零布局，
    显示/隐藏完全交给每个气泡自己的 `hidden`。
    """
    if not notes:
        return ""
    rows = "".join(
        f'<div class="{TNOTE_CLASS}-bubble" id="tn-{html.escape(nid, quote=True)}" hidden>'
        f'<span class="{TNOTE_CLASS}-label">译注</span>'
        f'<span class="{TNOTE_CLASS}-body">{html.escape(text)}</span></div>'
        for nid, text in notes.items()
    )
    return f'<div class="{TNOTE_STORE_CLASS}">{rows}</div>'


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
        elif name == "tn":
            # [译者注] 只在中文栏出现。气泡本体由 build_site 统一挂在章尾，
            # 这里只给出触发点；tabindex + aria 让键盘和读屏也能用。
            if closing:
                out.append("</span>")
            else:
                nm = re.search(r'note="([^"]*)"', attrs)
                note = html.escape(nm.group(1), quote=True) if nm else ""
                out.append(
                    f'<span class="tnote" tabindex="0" role="button" note="{note}"'
                    f' aria-expanded="false">')
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
