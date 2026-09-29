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
  * 虚构语言（Dzegoban 罗马字）片段标记 locked，不送翻译。
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
# 会承载文字、且通常不含块级子节点的容器
LEAF_ROLES = {
    "p": "p", "h1": "title", "h2": "h2", "h3": "h3", "h4": "h4",
    "li": "li", "td": "cell", "th": "th", "button": "button",
    "pre": "pre", "blockquote": "quote", "center": "center", "b": "b",
}

CONLANG_FONT_RE = re.compile(r"TeX Gyre Chorus", re.I)
CONLANG_TEXT_RE = re.compile(r"^[a-z][a-z\s&nbsp;]*$")

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
    return "".join(f' {k}="{esc_attr(v)}"' for k, v in attrs.items() if v != "")


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

    def new_block_id(self) -> str:
        self.bn += 1
        return f"{self.pad}-b{self.bn:04d}"

    # ---------- mini-markup ----------
    def inline_markup(self, node: Node) -> str:
        out = []
        for c in node.children:
            if isinstance(c, str):
                out.append(esc_text(re.sub(r"[\t\r\n]+", " ", c)))
            elif c.tag == "br":
                out.append("<br/>")
            elif c.tag == "span":
                style = c.attrs.get("style", "")
                inner = self.inline_markup(c)
                if not style:
                    out.append(inner)
                elif CONLANG_FONT_RE.search(style) and CONLANG_TEXT_RE.match(c.texts().strip() or "x"):
                    out.append(f"<f>{inner}</f>")
                else:
                    out.append(f'<c st="{esc_attr(style)}">{inner}</c>')
            elif c.tag in ("b", "strong"):
                out.append(f"<b>{self.inline_markup(c)}</b>")
            elif c.tag in ("i",):
                out.append(f"<i>{self.inline_markup(c)}</i>")
            elif c.tag in ("em",):
                out.append(f"<e>{self.inline_markup(c)}</e>")
            elif c.tag in ("sup", "sub", "code", "u", "small", "mark"):
                out.append(f"<{c.tag}>{self.inline_markup(c)}</{c.tag}>")
            elif c.tag == "a":
                href = c.attrs.get("href", "")
                out.append(f'<a href="{esc_attr(href)}">{self.inline_markup(c)}</a>')
            elif c.tag in VOID:
                continue
            else:  # 兜底：丢掉标签保留内容
                out.append(self.inline_markup(c))
        s = "".join(out)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def is_locked(self, node: Node) -> bool:
        """虚构语言（Dzegoban 罗马字）片段：pre / dz-line 或整段用 Chorus 字体。"""
        if node.tag == "pre":
            return True
        if "dz-line" in node.cls():
            return True
        return False

    # ---------- 结构 ----------
    def render(self, node: Node, segs_here: list[str]) -> str:
        """把一个结构节点渲染成骨架 HTML，叶子容器转成片段。"""
        if node.tag in VOID:
            return f"<{node.tag}{attr_str(node.attrs)}>" if node.tag != "br" else "<br/>"
        if node.tag in ("script", "style", "nav"):
            return ""
        if node.tag in ("input",):
            return f"<input{attr_str({k: v for k, v in node.attrs.items() if k in ('type', 'style')})}>"
        # 叶子容器 -> 单片段
        if not has_block_child(node) and node.tag in LEAF_ROLES or (
            not has_block_child(node) and node.tag == "div"
        ):
            markup = self.inline_markup(node)
            if markup == "":
                return ""
            roles = LEAF_ROLES.get(node.tag)
            role = roles or ("div" if "dz-card" in node.cls() else "div")
            locked = self.is_locked(node)
            seg = self.new_seg(role, markup, locked=locked,
                               note="conlang" if locked else "")
            segs_here.append(seg)
            return f"<{node.tag}{attr_str(self.out_attrs(node))}>{seg}</{node.tag}>"
        # 结构节点：递归
        inner = []
        for c in node.children:
            if isinstance(c, str):
                t = c.strip()
                if t:
                    seg = self.new_seg("div", esc_text(re.sub(r"\s+", " ", t)))
                    segs_here.append(seg)
                    inner.append(seg)
            else:
                inner.append(self.render(c, segs_here))
        body = "".join(x for x in inner if x)
        if body == "":
            return ""
        if node.tag == "br":
            return "<br/>"
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
        markup = self.inline_markup(node)
        if markup == "":
            return {"id": self.new_block_id(), "kind": "empty"}
        role = LEAF_ROLES.get(node.tag, kind)
        seg = self.new_seg(role, markup, locked=self.is_locked(node))
        segs.append(seg)
        return {"id": self.new_block_id(), "kind": kind,
                "skeleton": f"<{node.tag}>{seg}</{node.tag}>", "segs": segs}

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
                if txt_direct and date is None and place is None:
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


def parse_chapter(path: Path) -> Node:
    raw = path.read_text(encoding="utf-8")
    i = raw.find('<div class="document-page">')
    if i < 0:
        i = raw.find('<div class="document-page"')
    j = raw.rfind("</div>")
    body = raw[i:j + 6]
    b = DomBuilder()
    b.feed(body)
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
    return {"chapter": chapter, "blocks": len(blocks), "segs": len(ex.segs),
            "locked": sum(1 for s in ex.segs if s["locked"]), "figures": len(ex.figures)}


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
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
