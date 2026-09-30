#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把「结构骨架 + 中文片段」组装成 Markdown（逐章）与全书单文件。

用法:
    python3 pipeline/build_markdown.py            # 组装全部已译章节
    python3 pipeline/build_markdown.py 1 2 3      # 指定章
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAP_DIR = ROOT / "sources" / "work" / "chapters"
ZH_DIR = ROOT / "translations" / "zh"
FIG_MANIFEST = ROOT / "sources" / "work" / "figures" / "manifest.json"
BOOK = ROOT / "book"
BOOK_CH = BOOK / "chapters"

TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")

CN_NUM = "零一二三四五六七八九十".split() if False else None


def cn_num(n: int) -> str:
    """1..99 的中文数字，用于「第三章」。"""
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    tens, ones = divmod(n, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def oklch_to_hex(style: str) -> str:
    """把 oklch(L C H) 颜色转成 #rrggbb，兼容不支持 oklch 的渲染器。"""

    def conv(m: re.Match) -> str:
        L, C, H = float(m.group(1)), float(m.group(2)), float(m.group(3))
        a = C * math.cos(math.radians(H))
        b = C * math.sin(math.radians(H))
        l_ = L + 0.3963377774 * a + 0.2158037573 * b
        m_ = L - 0.1055613458 * a - 0.0638541728 * b
        s_ = L - 0.0894841775 * a - 1.2914855480 * b
        l, m2, s = l_ ** 3, m_ ** 3, s_ ** 3
        r = 4.0767416621 * l - 3.3077115913 * m2 + 0.2309699292 * s
        g = -1.2684380046 * l + 2.6097574011 * m2 - 0.3413193965 * s
        bb = -0.0041960863 * l - 0.7034186147 * m2 + 1.7076147010 * s

        def gamma(x: float) -> float:
            x = max(0.0, min(1.0, x))
            return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

        return "#%02x%02x%02x" % tuple(int(round(gamma(v) * 255)) for v in (r, g, bb))

    return re.sub(r"oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)", conv, style)


MD_ESCAPE = re.compile(r"([\\`*_\[\]])")


def mini_to_md(text: str) -> str:
    """mini-markup → Markdown / 内联 HTML。

    [用户请求] 中文不用斜体：本书是中文成品，`<e>`/`<i>`（原文着重）一律落成加粗 `**`，
    不再输出 `*…*`。见 docs/style-guide.md §2。
    """
    out: list[str] = []
    pos = 0
    links: list[str] = []
    for m in TAG_RE.finditer(text):
        out.append(MD_ESCAPE.sub(r"\\\1", text[pos:m.start()]))
        pos = m.end()
        closing, name, attrs, selfclose = m.groups()
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
            out.append("**")
        elif name in ("i", "e"):
            out.append("**")
        elif name == "code":
            out.append("`")
        elif name == "a":
            if closing:
                out.append(f"]({links.pop() if links else ''})")
            else:
                hm = re.search(r'href="([^"]*)"', attrs)
                links.append(hm.group(1) if hm else "")
                out.append("[")
        elif name in ("sup", "sub", "u", "small", "mark"):
            out.append(f"<{name}>" if not closing else f"</{name}>")
    out.append(MD_ESCAPE.sub(r"\\\1", text[pos:]))
    return "".join(out)


def expand(skeleton: str, segs: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: mini_to_md(segs.get(m.group(1), "")), skeleton)


def clean_ws(s: str) -> str:
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def build_chapter(ch: int, segs: dict[str, str]) -> str | None:
    cf = CHAP_DIR / f"chapter-{ch:02d}.json"
    if not cf.exists():
        return None
    data = json.loads(cf.read_text(encoding="utf-8"))
    captions: dict[str, str] = {}
    if FIG_MANIFEST.exists():
        man = json.loads(FIG_MANIFEST.read_text(encoding="utf-8"))
        captions = {k: v.get("caption", "") for k, v in man.items()}
    parts: list[str] = []
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind == "title":
            parts.append(f"# 第{cn_num(ch)}章\n")
        elif kind in ("dateline-open", "scene-break"):
            ids = [m.group(1) for m in PLACEHOLDER_RE.finditer("".join(blk.get("segs", [])))]
            vals = [segs.get(i, "") for i in ids]
            vals = [v for v in vals if v]
            line = " · ".join(vals)
            cls = "dateline" if kind == "dateline-open" else "scene-break"
            if kind == "scene-break":
                parts.append("---\n")
            parts.append(f'<p class="{cls}">{mini_to_md(line)}</p>\n')
        elif kind == "rule":
            parts.append("---\n")
        elif kind == "figure":
            figs = blk.get("figures", [])
            for f in figs:
                name = f[:-4]
                cap = captions.get(name, "")
                alt = cap or f"插图 {name}"
                parts.append(f"![{alt}](../images/{f})\n")
            if blk.get("skeleton"):
                parts.append(expand(blk["skeleton"], segs) + "\n")
        elif kind in ("p",):
            html = expand(blk.get("skeleton", ""), segs)
            inner = re.sub(r"^<p>|</p>$", "", html)
            parts.append(inner + "\n")
        else:
            parts.append(expand(blk.get("skeleton", ""), segs) + "\n")
    return clean_ws("\n".join(parts))


def load_segs(ch: int) -> dict[str, str]:
    p = ZH_DIR / f"chapter-{ch:02d}.zh.json"
    if not p.exists():
        return {}
    return {s["id"]: s["text"] for s in json.loads(p.read_text(encoding="utf-8"))["segments"]}


FRONT = """# 雪月 Snowmoon · 中文版

> 原作：**Snowmoon**，作者 Vitalik Buterin（<https://vitalik.eth.limo/snowmoon/>），
> 以 GPL-3.0-only 发布。
>
> 本文件是非官方中译本：正文由英文原文译出，插图由英文版重绘为中文版。
> 译文与重绘均未获原作者审定。本项目同样以 GPL-3.0-only 发布，
> 详见仓库根目录 `LICENSE` 与 `docs/licensing.md`。

**目录**

"""


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    BOOK_CH.mkdir(parents=True, exist_ok=True)
    built = []
    toc = []
    for ch in todo:
        segs = load_segs(ch)
        if not segs:
            print(f"skip ch{ch:02d}（无译文）")
            continue
        md = build_chapter(ch, segs)
        if md is None:
            continue
        (BOOK_CH / f"chapter-{ch:02d}.md").write_text(md + "\n", encoding="utf-8")
        built.append(ch)
        toc.append(f"- [第{cn_num(ch)}章](chapters/chapter-{ch:02d}.md)")
    if built:
        book = FRONT + "\n".join(toc) + "\n\n"
        for ch in built:
            segs = load_segs(ch)
            book += "\n\n---\n\n" + build_chapter(ch, segs) + "\n"
        (BOOK / "snowmoon-zh.md").write_text(book, encoding="utf-8")
    print(f"组装完成：{len(built)} 章 → book/snowmoon-zh.md")


if __name__ == "__main__":
    main()
