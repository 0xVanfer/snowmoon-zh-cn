#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Snowmoon 中译流水线 · 第一步：结构抽取

把上游英文 HTML（sources/en/html/chapter-N.html）解析成"结构 + 可译片段"两层：

  sources/work/chapters/chapter-NN.json   结构骨架（不可变）：块 + 带 {{S:id}} 占位的骨架 HTML
  sources/work/segments/chapter-NN.src.json  可译片段（英文原文，逐条 id）
  sources/work/figures/chapter-NN-fig-XX.svg 插图原始 SVG

设计要点见 docs/pipeline.md：
  * 结构（标签、样式、表格布局）与文字彻底分离，翻译时只动文字，杜绝结构漂移；
  * 内联文字用受限 mini-markup 表达（见 docs/style-guide.md），便于校验和回写；
  * 虚构语言（Dzegoban 罗马字）片段标记 locked，不送翻译：有 `pre` / `dz-line` 标记的直接判定，
    没有标记的（散落在普通 <p>/<td> 里）用 sources/work/conlang_vocab.json 词表识别；
    词表覆盖不到的泽国语变体由 validate_translation.py 的兜底规则放行。
"""
from __future__ import annotations

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "en" / "html"
WORK = ROOT / "sources" / "work"

VOID = {
    "br", "hr", "img", "input", "meta", "link", "col", "source",
    "path", "rect", "line", "circle", "polygon", "polyline", "ellipse",
    "use", "stop", "animate", "animateTransform", "set",
}
# 内联（非块级）标签白名单：保留在可译片段内部
INLINE = {"span", "b", "strong", "i", "em", "sup", "sub", "code", "a", "br", "u", "small", "mark", "abbr"}
# 块级标签：递归进入结构
BLOCK = {"p", "div", "table", "thead", "tbody", "tfoot", "tr", "td", "th",
         "ul", "ol", "li", "blockquote", "center", "h1", "h2", "h3", "h4", "h5", "h6",
         "pre", "figure", "figcaption", "section", "article", "b", "hr", "button"}
# 空元素也必须在骨架里保留的「占位槽」：丢了会破坏表格列数／列表编号
EMPTY_KEEP = {"td", "th", "li", "a", "button"}
# 会承载文字、且通常不含块级子节点的容器
LEAF_ROLES = {
    "p": "p", "h1": "title", "h2": "h2", "h3": "h3", "h4": "h4",
    "li": "li", "td": "cell", "th": "th", "button": "button",
    "pre": "pre", "blockquote": "quote", "center": "center", "b": "b",
}

CONLANG_FONT_RE = re.compile(r"TeX Gyre Chorus", re.I)
CONLANG_TEXT_RE = re.compile(r"^[a-z][a-z\s&nbsp;]*$")
# 泽国语词表（由 build_conlang_vocab.py 生成）。用于识别「没有 dz-line / Chorus 字体标记」
# 的虚构语言片段——这类文字散落在普通 <p>/<td> 里，只靠标签无从判断，必须靠词表。
# [P0] 词表缺失 / 损坏时此前只把 CONLANG_VOCAB 置空、不留任何痕迹：词表识别**整体**
# 静默失效，散落在普通段落里的虚构语言会被当成待译英文送去翻译，而 extract 照常
# exit 0。这里把「为什么是空的」记下来，交给 main() 决定要不要硬失败。
CONLANG_VOCAB: set[str] = set()
CONLANG_VOCAB_PROBLEM: str | None = None
_cv = ROOT / "sources" / "work" / "conlang_vocab.json"
if not _cv.exists():
    CONLANG_VOCAB_PROBLEM = f"缺少词表 {_cv.relative_to(ROOT)}（先跑 build_conlang_vocab.py）"
else:
    try:
        CONLANG_VOCAB = {w.lower() for w in json.loads(_cv.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        CONLANG_VOCAB_PROBLEM = f"词表 {_cv.relative_to(ROOT)} 解析失败: {exc}"
# 布局容器：flex/grid 的子元素各自是独立布局项，绝不能把子元素拍平成一个文本节点
# （典型：投票/拖动条的 `display:flex; justify-content:space-between` 刻度行）。
LAYOUT_RE = re.compile(r"display\s*:\s*(?:flex|grid)|justify-content", re.I)

# 只出现在页面结构里、绝不该出现在 <svg> 内部的 HTML 标签。
# 出现即说明上游有未闭合的 <svg>，把后续兄弟节点吞进了图里（见 docs/lessons.md）。
# [P0] 行内标签此前整类缺席：被吞掉的段落若只用 <b>/<i>/<a>/<code> 排版，这张守卫
# 完全看不见——该段正文变成 0 片段、全文进 .svg，而 extract 照常 exit 0。
# SVG 里合法的标签只有 svg 自身那一族（text/tspan/path/g/…），这些 HTML 标签一律不算。
HTML_ONLY_TAGS = {
    "p", "div", "span", "table", "thead", "tbody", "tfoot", "tr", "td", "th",
    "figure", "figcaption", "blockquote", "center", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "button", "pre",
    # 行内 / 文本级：同样绝不该出现在 <svg> 内部
    "b", "strong", "i", "em", "u", "s", "strike", "a", "code", "kbd", "samp",
    "var", "small", "big", "sub", "sup", "abbr", "cite", "q", "mark", "time",
    "label", "legend", "fieldset", "form", "input", "select", "option",
    "textarea", "dl", "dt", "dd", "details", "summary", "main", "header",
    "footer", "nav", "aside", "hr", "br", "wbr", "font", "caption", "col",
    "colgroup", "video", "audio", "iframe", "canvas", "noscript", "picture",
}


# 与英语常用词同形的泽国语音节：出现即放弃判定，交给校验脚本的兜底规则处理。
ENGLISH_LOOKALIKE = {
    "a", "am", "an", "and", "are", "as", "at", "be", "but", "by", "can", "die", "do",
    "for", "from", "go", "had", "has", "he", "her", "hi", "him", "his", "if", "in",
    "is", "it", "me", "min", "my", "no", "not", "of", "on", "or", "our", "out", "she",
    "so", "ten", "than", "that", "the", "them", "then", "they", "this", "to", "up",
    "us", "was", "we", "who", "why", "with", "you",
}


def looks_like_conlang(text: str) -> bool:
    """判断一段纯文本是否为「未加标记的泽国语罗马字」。

    规则（保守，宁可漏判不可误判——误判会把已翻译的片段锁死）：
      * 含汉字则不是；
      * 至少两个词（单词多半是人名／界面 token，如 Fin / Bai，它们确实要翻译）；
      * 除句首外不出现大写（排除 TEI / MUG 这类缩写）；
      * 不含与英语常用词同形的音节（如 ten min 实为「10 分钟」，已被译出）；
      * 所有词都在泽国语词表内。
    漏判是可以接受的（校验脚本仍有兜底），误判会直接让已翻译的章节校验失败。
    """
    if not CONLANG_VOCAB:
        return False
    body = re.sub(r"<[^>]+>", " ", text or "")
    if re.search(r"[\u3400-\u9fff]", body):
        return False
    toks = re.findall(r"[A-Za-z]+", body)
    if len(toks) < 2:
        return False
    for t in toks:
        if t[1:] != t[1:].lower():
            return False
    low = [t.lower() for t in toks]
    if any(t in ENGLISH_LOOKALIKE for t in low):
        return False
    return all(t in CONLANG_VOCAB for t in low)

# HTMLParser 把标签/属性名统一转小写；SVG 是 XML，必须还原大小写，否则 viewBox / clipPath 失效。
SVG_TAG_CASE = {
    "clippath": "clipPath", "lineargradient": "linearGradient", "radialgradient": "radialGradient",
    "textpath": "textPath", "foreignobject": "foreignObject",
    "animatetransform": "animateTransform", "animatemotion": "animateMotion", "mpath": "mpath",
    "fegaussianblur": "feGaussianBlur", "fecolormatrix": "feColorMatrix", "fecomposite": "feComposite",
    "feblend": "feBlend", "feoffset": "feOffset", "femerge": "feMerge", "femergenode": "feMergeNode",
    "feflood": "feFlood", "feturbulence": "feTurbulence", "fedisplacementmap": "feDisplacementMap",
    "fedropshadow": "feDropShadow", "femorphology": "feMorphology", "feimage": "feImage",
}
SVG_ATTR_CASE = {
    "viewbox": "viewBox", "preserveaspectratio": "preserveAspectRatio",
    "attributename": "attributeName", "attributetype": "attributeType",
    "calcmode": "calcMode", "keytimes": "keyTimes", "keysplines": "keySplines", "keypoints": "keyPoints",
    "markerheight": "markerHeight", "markerwidth": "markerWidth", "markerunits": "markerUnits",
    "patternunits": "patternUnits", "patterncontentunits": "patternContentUnits",
    "patterntransform": "patternTransform", "refx": "refX", "refy": "refY",
    "repeatcount": "repeatCount", "repeatdur": "repeatDur", "restart": "restart",
    "gradientunits": "gradientUnits", "gradienttransform": "gradientTransform",
    "spreadmethod": "spreadMethod", "clippathunits": "clipPathUnits",
    "maskunits": "maskUnits", "maskcontentunits": "maskContentUnits",
    "filterunits": "filterUnits", "primitiveunits": "primitiveUnits",
    "stddeviation": "stdDeviation", "basefrequency": "baseFrequency", "numoctaves": "numOctaves",
    "surfacescale": "surfaceScale", "specularconstant": "specularConstant",
    "specularexponent": "specularExponent", "diffuseconstant": "diffuseConstant",
    "kernelmatrix": "kernelMatrix", "kernelunitlength": "kernelUnitLength",
    "xchannelselector": "xChannelSelector", "ychannelselector": "yChannelSelector",
    "startoffset": "startOffset", "textlength": "textLength", "lengthadjust": "lengthAdjust",
    "pathlength": "pathLength", "targetx": "targetX", "targety": "targetY",
    "zoomandpan": "zoomAndPan", "contentscripttype": "contentScriptType",
    "requiredfeatures": "requiredFeatures", "requiredextensions": "requiredExtensions",
    "systemlanguage": "systemLanguage", "externalresourcesrequired": "externalResourcesRequired",
    "xlink:href": "xlink:href", "xml:space": "xml:space",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []
        self.parent = parent

    def __repr__(self):  # pragma: no cover
        return f"<{self.tag} {self.attrs} children={len(self.children)}>"

    def cls(self) -> str:
        return self.attrs.get("class", "")

    def texts(self) -> str:
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.texts())
        return "".join(out)


class DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def esc_text(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_attr(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def attr_str(attrs: dict[str, str]) -> str:
    # 空值属性（布尔属性 checked/disabled、class="" 等）一并保留：
    # 丢掉它们会静默改变语义与样式。
    return "".join(f' {k}="{esc_attr(v)}"' for k, v in attrs.items())


def has_block_child(node: Node) -> bool:
    for c in node.children:
        if isinstance(c, Node) and c.tag in BLOCK:
            return True
    return False


class Extractor:
    def __init__(self, chapter: int):
        self.chapter = chapter
        self.pad = f"c{chapter:02d}"
        self.segs: list[dict] = []
        self.figures: list[dict] = []
        self.bn = 0
        self.sn = 0
        self.fn = 0

    # ---------- 片段 ----------
    def new_seg(self, role: str, markup: str, locked: bool = False, note: str = "") -> str:
        self.sn += 1
        sid = f"{self.pad}-s{self.sn:04d}"
        self.segs.append({"id": sid, "role": role, "text": markup, "locked": locked, "note": note})
        return f"{{{{S:{sid}}}}}"

    def seg_in(self, role: str, markup: str, ctx: list | None,
               locked: bool = False, note: str = "") -> str:
        """在布局容器内部创建片段。

        ctx = [已用数量, 基准 id]。容器内的第一个片段占用一个正常的自增序号作为基准 id，
        第 2..n 个片段用 `基准id#k`；容器外的片段编号完全不受影响，
        已有译文的 id 不会漂移。基准 id 在第一个片段出现时才占用，空容器不占号。
        """
        if ctx is None:
            return self.new_seg(role, markup, locked=locked, note=note)
        if ctx[1] is None:
            self.sn += 1
            ctx[1] = f"{self.pad}-s{self.sn:04d}"
        ctx[0] += 1
        sid = ctx[1] if ctx[0] == 1 else f"{ctx[1]}#{ctx[0]}"
        self.segs.append({"id": sid, "role": role, "text": markup, "locked": locked, "note": note})
        return f"{{{{S:{sid}}}}}"

    def new_block_id(self) -> str:
        self.bn += 1
        return f"{self.pad}-b{self.bn:04d}"

    # ---------- mini-markup ----------
    def inline_markup(self, node: Node, preserve_ws: bool = False) -> str:
        """把节点的内联内容转成 mini-markup。

        preserve_ws=True 用于 <pre>：空白与换行是内容的一部分（字符画／排版），
        必须原样保留；其余场景把连续空白折叠成单个空格。
        """
        out = []
        for c in node.children:
            if isinstance(c, str):
                out.append(esc_text(c if preserve_ws else re.sub(r"[\t\r\n]+", " ", c)))
            elif c.tag in ("script", "style", "nav"):
                continue  # 叶子容器里的脚本/样式不得漏进可译文本
            elif c.tag == "br":
                out.append("<br/>")
            elif c.tag == "span":
                style = c.attrs.get("style", "")
                inner = self.inline_markup(c, preserve_ws)
                if not style:
                    out.append(inner)
                elif CONLANG_FONT_RE.search(style) and CONLANG_TEXT_RE.match(c.texts().strip() or "x"):
                    out.append(f"<f>{inner}</f>")
                else:
                    out.append(f'<c st="{esc_attr(style)}">{inner}</c>')
            elif c.tag in ("b", "strong"):
                out.append(f"<b>{self.inline_markup(c, preserve_ws)}</b>")
            elif c.tag in ("i",):
                out.append(f"<i>{self.inline_markup(c, preserve_ws)}</i>")
            elif c.tag in ("em",):
                out.append(f"<e>{self.inline_markup(c, preserve_ws)}</e>")
            elif c.tag in ("sup", "sub", "code", "u", "small", "mark"):
                out.append(f"<{c.tag}>{self.inline_markup(c, preserve_ws)}</{c.tag}>")
            elif c.tag == "a":
                href = c.attrs.get("href", "")
                out.append(f'<a href="{esc_attr(href)}">{self.inline_markup(c, preserve_ws)}</a>')
            elif c.tag in VOID:
                continue
            else:  # 兜底：丢掉标签保留内容
                out.append(self.inline_markup(c, preserve_ws))
        s = "".join(out)
        if preserve_ws:
            # 只裁掉 <pre> 首尾的换行（HTML 规定标签后紧跟的换行不参与渲染），内部原样
            return s.strip("\n")
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def is_locked(self, node: Node) -> bool:
        """不可翻译片段：<pre> / dz-line / 未加标记的泽国语罗马字。"""
        if node.tag == "pre":
            return True
        if "dz-line" in node.cls():
            return True
        return looks_like_conlang(node.texts())

    # ---------- 结构 ----------
    def render(self, node: Node, segs_here: list[str], ctx: list | None = None) -> str:
        """把一个结构节点渲染成骨架 HTML，叶子容器转成片段。

        ctx 非空表示当前位于某个布局容器（flex/grid）内部，片段用子编号。
        """
        if node.tag in VOID:
            return f"<{node.tag}{attr_str(node.attrs)}>" if node.tag != "br" else "<br/>"
        if node.tag in ("script", "style", "nav"):
            return ""
        # 布局容器（flex/grid）：子元素必须逐个保留，否则 space-between 之类会失效
        if not has_block_child(node) and LAYOUT_RE.search(
                node.attrs.get("style", "") + " " + node.attrs.get("class", "")):
            return self.render_layout_items(node, segs_here, [0, None])
        # 叶子容器 -> 单片段
        if not has_block_child(node) and (node.tag in LEAF_ROLES or node.tag == "div"):
            markup = self.inline_markup(node, preserve_ws=(node.tag == "pre"))
            if markup == "":
                # 空单元格/空列表项是**占位槽**：丢掉会让整行的列数变少、
                # 后面的单元格整体左移（第 15 章 17 个空 <th> 就是这样丢的）。
                if node.tag in EMPTY_KEEP:
                    return f"<{node.tag}{attr_str(self.out_attrs(node))}></{node.tag}>"
                return ""
            role = LEAF_ROLES.get(node.tag) or "div"
            locked = self.is_locked(node)
            seg = self.seg_in(role, markup, ctx, locked=locked,
                              note="conlang" if locked else "")
            segs_here.append(seg)
            return f"<{node.tag}{attr_str(self.out_attrs(node))}>{seg}</{node.tag}>"
        # 结构节点：递归
        inner = []
        for c in node.children:
            if isinstance(c, str):
                t = c.strip()
                if t:
                    seg = self.seg_in("div", esc_text(re.sub(r"\s+", " ", t)), ctx)
                    segs_here.append(seg)
                    inner.append(seg)
            else:
                inner.append(self.render(c, segs_here, ctx))
        body = "".join(x for x in inner if x)
        if body == "":
            return ""
        if node.tag == "br":
            return "<br/>"
        return f"<{node.tag}{attr_str(self.out_attrs(node))}>{body}</{node.tag}>"

    def render_layout_items(self, node: Node, segs_here: list[str], ctx: list) -> str:
        """渲染布局容器的直接子元素：每个子元素保持为独立元素（独立布局项），
        其内部文字用受限 mini-markup 表示，成为一个片段。"""
        parts: list[str] = []
        for c in node.children:
            if isinstance(c, str):
                if c.strip() == "":
                    # 原文元素之间有空白；flex 会忽略它，但 Markdown 等非 flex 场景需要它分隔
                    parts.append(" ")
                    continue
                seg = self.seg_in("div", esc_text(re.sub(r"\s+", " ", c)).strip(), ctx)
                segs_here.append(seg)
                parts.append(seg)
                continue
            if c.tag in ("script", "style", "nav"):
                continue
            if c.tag in VOID or has_block_child(c):
                parts.append(self.render(c, segs_here, ctx))
                continue
            inner = self.inline_markup(c)
            attrs = attr_str(self.out_attrs(c))
            if inner == "":
                parts.append(f"<{c.tag}{attrs}></{c.tag}>")  # 空项也要保留，否则项数不对
                continue
            locked = self.is_locked(c)
            seg = self.seg_in("div", inner, ctx, locked=locked, note="conlang" if locked else "")
            segs_here.append(seg)
            parts.append(f"<{c.tag}{attrs}>{seg}</{c.tag}>")
        body = "".join(p for p in parts if p)
        if body == "":
            return ""
        return f"<{node.tag}{attr_str(self.out_attrs(node))}>{body}</{node.tag}>"

    @staticmethod
    def out_attrs(node: Node) -> dict[str, str]:
        keep = {}
        for k, v in node.attrs.items():
            if k in ("style", "class", "colspan", "rowspan", "href", "title", "alt"):
                keep[k] = v
        return keep

    # ---------- 顶层块 ----------
    def blocks(self, page: Node) -> list[dict]:
        out: list[dict] = []
        for node in page.children:
            if isinstance(node, str):
                continue
            if not isinstance(node, Node):
                continue
            if node.tag in ("script", "style", "nav", "button"):
                continue
            cls = node.cls()
            if node.tag == "h1":
                out.append(self.simple_block("title", node))
            elif node.tag == "div" and "dateline" in cls:
                out.append(self.dateline_block(node))
            elif node.tag == "hr":
                out.append({"id": self.new_block_id(), "kind": "rule"})
            elif node.tag == "br":
                continue  # 纯排版空行
            elif node.tag == "div" and "device-view" in cls:
                out.append(self.device_block(node))
            elif node.tag == "p":
                out.append(self.simple_block("p", node))
            elif node.tag == "blockquote":
                out.append(self.struct_block("blockquote", node))
            elif node.tag == "center":
                out.append(self.struct_block("center", node))
            elif node.tag in ("ul", "ol"):
                out.append(self.struct_block("list", node))
            elif node.tag == "table":
                out.append(self.struct_block("panel", node))
            else:
                out.append(self.struct_block("other", node))
        return out

    def simple_block(self, kind: str, node: Node) -> dict:
        segs: list[str] = []
        markup = self.inline_markup(node, preserve_ws=(node.tag == "pre"))
        if markup == "":
            return {"id": self.new_block_id(), "kind": "empty"}
        role = LEAF_ROLES.get(node.tag, kind)
        locked = self.is_locked(node)
        seg = self.new_seg(role, markup, locked=locked, note="conlang" if locked else "")
        segs.append(seg)
        return {"id": self.new_block_id(), "kind": kind,
                "skeleton": f"<{node.tag}{attr_str(self.out_attrs(node))}>{seg}</{node.tag}>",
                "segs": segs}

    def struct_block(self, kind: str, node: Node) -> dict:
        segs: list[str] = []
        skeleton = self.render(node, segs)
        return {"id": self.new_block_id(), "kind": kind, "skeleton": skeleton, "segs": segs}

    def dateline_block(self, node: Node) -> dict:
        place = date = None
        for sp in node.children:
            if isinstance(sp, Node) and sp.tag == "span" and "txt" in sp.cls():
                for s2 in sp.children:
                    if isinstance(s2, Node):
                        if "place" in s2.cls():
                            place = s2.texts().strip()
                        elif "date" in s2.cls():
                            date = s2.texts().strip()
                txt_direct = "".join(c for c in sp.children if isinstance(c, str)).strip()
                # 裸文本兜底：既要覆盖「完全没有 place/date 子 span」的情形，
                # 也要覆盖「有 place span + 裸文本日期」（如第 26 章 `…</span>·</span>3724 Frostime 6`）——
                # 旧条件额外要求 place is None，导致这种日期被整段丢弃。
                if txt_direct and date is None:
                    date = re.sub(r"\s+", " ", txt_direct)
        segs: list[str] = []
        if place:
            segs.append(self.new_seg("place", esc_text(place)))
        if date:
            segs.append(self.new_seg("date", esc_text(date)))
        kind = "dateline-open" if "chapter-open" in node.cls() else "scene-break"
        return {"id": self.new_block_id(), "kind": kind, "segs": segs,
                "place": place, "date": date}

    # ---------- 插图 ----------
    def device_block(self, node: Node) -> dict:
        cls = node.cls()
        layout = "left" if "device-view-left" in cls else "center"
        width = "wide" if "wide-device-view" in cls else "narrow"
        svgs = [c for c in node.children if isinstance(c, Node) and c.tag == "svg"]
        if svgs:
            figs = []
            for svg in svgs:
                # 上游若有未闭合的 <svg>，HTMLParser 会把后续兄弟节点挂进 svg 里，
                # 正文会拿不到片段 id 并连带被写进插图文件。这里显式拦下，宁可报错也不静默吞内容。
                # [P1] 但 <foreignObject> **合法地**包含 HTML（div/p/span/table…）。
                # 不区分结构的话，一个完全正常的 <svg><foreignObject><div>…</div></foreignObject></svg>
                # 会被判成「未闭合，吞入了页面元素」，整章抽取直接中止。
                # 只检查 foreignObject **之外**的 HTML 标签。
                leaked = sorted({d.tag for d in descendants(svg)
                                 if d.tag in HTML_ONLY_TAGS
                                 and not inside_foreign_object(svg, d)})
                if leaked:
                    raise SystemExit(
                        f"chapter-{self.chapter}: <svg> 未闭合，吞入了页面元素 {leaked}；"
                        f"请先修复上游 HTML 再抽取")
                self.fn += 1
                fname = f"chapter-{self.chapter:02d}-fig-{self.fn:02d}.svg"
                svg_src = serialize_svg(svg)
                self.figures.append({"file": fname, "chapter": self.chapter,
                                     "index": self.fn, "layout": layout, "width": width,
                                     "svg": svg_src})
                figs.append(fname)
            # 同一 device-view 里除 SVG 外的可读内容（表格兜底等）也保留为文字块
            rest = Node("div", {"class": cls})
            for c in node.children:
                if isinstance(c, Node) and c.tag == "svg":
                    continue
                rest.children.append(c)
            block = {"id": self.new_block_id(), "kind": "figure", "figures": figs, "layout": layout}
            leftover_segs: list[str] = []
            leftover = self.render(rest, leftover_segs) if rest.children else ""
            if leftover:
                block["skeleton"] = leftover
                block["segs"] = leftover_segs
            return block
        return self.struct_block("panel", node)


def descendants(node: Node):
    """深度优先后代节点（不含自身）。"""
    for c in node.children:
        if isinstance(c, Node):
            yield c
            yield from descendants(c)


def inside_foreign_object(svg: Node, target: Node) -> bool:
    """target 是否位于某个 <foreignObject> 之内。

    <foreignObject> 是 SVG 规范里嵌 HTML 的合法容器，它内部的 div/p/span/table
    不是「未闭合 <svg> 吞进来的页面元素」，不该被 SVG 泄漏守卫拦下。

    HTMLParser 会把标签名转小写，所以判 `foreignobject`。
    """
    def walk(node: Node, inside: bool) -> bool:
        for c in node.children:
            if not isinstance(c, Node):
                continue
            if c is target:
                return inside
            # 进入 foreignobject 即进入「合法 HTML 区」；其内部继续按普通子树走，
            # 嵌套的 foreignobject 仍是合法区。
            if walk(c, inside or c.tag == "foreignobject"):
                return True
        return False

    return walk(svg, False)


def serialize_svg(node: Node) -> str:
    """序列化 SVG。HTMLParser 会把标签/属性名转小写，这里恢复 SVG 的大小写敏感性。"""

    def rec(n: Node | str) -> str:
        if isinstance(n, str):
            return esc_text(n)
        tag = SVG_TAG_CASE.get(n.tag, n.tag)
        attrs = {SVG_ATTR_CASE.get(k, k): v for k, v in n.attrs.items()}
        if n.tag in VOID:
            return f"<{tag}{attr_str(attrs)}/>"
        return f"<{tag}{attr_str(attrs)}>" + "".join(rec(c) for c in n.children) + f"</{tag}>"

    return rec(node)


def slice_document_page(raw: str) -> str:
    """截出 <div class="document-page">…</div> 这一段。

    verify_extract.py 复用同一个函数，避免两处切片逻辑各自演化（历史 bug）。
    用正则找起始 div：原先写死 `class="document-page"` 必须是第一个属性，
    属性顺序一变就整段切片错位。
    """
    m = re.search(r'<div[^>]*\bclass="[^"]*\bdocument-page\b[^"]*"', raw)
    if not m:
        raise SystemExit("上游 HTML 里找不到 class 含 document-page 的 div")
    i = m.start()
    j = raw.rfind("</div>")
    if j < i:
        raise SystemExit("上游 HTML 结构异常：找不到 document-page 的结束标签")
    return raw[i:j + 6]


def parse_chapter(path: Path) -> Node:
    raw = path.read_text(encoding="utf-8")
    body = slice_document_page(raw)
    b = DomBuilder()
    b.feed(body)
    if not b.root.children or not isinstance(b.root.children[0], Node):
        raise SystemExit(f"{path}: 解析后没有根节点")
    page = b.root.children[0]
    assert isinstance(page, Node) and "document-page" in page.cls(), path
    return page


def process(chapter: int) -> dict:
    path = SRC / f"chapter-{chapter}.html"
    page = parse_chapter(path)
    ex = Extractor(chapter)
    blocks = ex.blocks(page)
    chap = {
        "chapter": chapter,
        "source_file": str(path.relative_to(ROOT)),
        "blocks": blocks,
        "figures": [f["file"] for f in ex.figures],
    }
    WORK.joinpath("chapters").mkdir(parents=True, exist_ok=True)
    WORK.joinpath("segments").mkdir(parents=True, exist_ok=True)
    WORK.joinpath("figures").mkdir(parents=True, exist_ok=True)
    (WORK / "chapters" / f"chapter-{chapter:02d}.json").write_text(
        json.dumps(chap, ensure_ascii=False, indent=1), encoding="utf-8")
    (WORK / "segments" / f"chapter-{chapter:02d}.src.json").write_text(
        json.dumps({"chapter": chapter, "segments": ex.segs}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    for f in ex.figures:
        (WORK / "figures" / f["file"]).write_text(f["svg"], encoding="utf-8")
    # 清理本章的陈旧插图：上游删图后旧文件会留在目录里，
    # make_figures.build() 是 glob 整个目录的，会为不存在的图白跑一次模型调用。
    keep = {f["file"] for f in ex.figures}
    for old in (WORK / "figures").glob(f"chapter-{chapter:02d}-fig-*.svg"):
        if old.name not in keep:
            old.unlink()
    return {"chapter": chapter, "blocks": len(blocks), "segs": len(ex.segs),
            "locked": sum(1 for s in ex.segs if s["locked"]), "figures": len(ex.figures)}


def discover_chapters() -> list[int]:
    """章号由磁盘上真实存在的上游 HTML 决定，而不是写死的 1..32。"""
    return sorted({int(m.group(1))
                   for m in (re.fullmatch(r"chapter-(\d+)\.html", p.name)
                             for p in SRC.glob("chapter-*.html"))
                   if m})


def main() -> None:
    # [P0] 上游原文不在时此前只跑一个空循环、打印全零 TOTAL 并 exit 0 ——
    # 「什么也没抽」被印成了「抽取成功」。verify_extract.py 对同一情况有显式处理。
    if not SRC.exists():
        raise SystemExit(f"缺少上游原文目录 {SRC.relative_to(ROOT)}：无从抽取。"
                         f"先放置 sources/en/html/chapter-N.html 再运行本脚本。")
    todo = [int(x) for x in sys.argv[1:]] or discover_chapters()
    # [P0] 词表缺席 = 虚构语言识别整体失效，必须在这里停住而不是让缺标记的泽国语
    # 被当成待译英文。--allow-missing-vocab 供「只想重跑部分章且知道后果」时显式放行。
    if CONLANG_VOCAB_PROBLEM and "--allow-missing-vocab" not in sys.argv[1:]:
        raise SystemExit(f"{CONLANG_VOCAB_PROBLEM}：泽国语识别会整体失效，"
                         f"散落在普通段落里的虚构语言会被当成待译英文。")
    if not todo:
        raise SystemExit(f"{SRC.relative_to(ROOT)} 下没有 chapter-N.html，没有可抽取的章节")
    total = {"blocks": 0, "segs": 0, "locked": 0, "figures": 0}
    for ch in todo:
        r = process(ch)
        for k in total:
            total[k] += r[k]
        print(f"ch{ch:02d}: blocks={r['blocks']:4d} segs={r['segs']:4d} "
              f"locked={r['locked']:3d} figures={r['figures']}")
    print("TOTAL", total)


if __name__ == "__main__":
    main()
