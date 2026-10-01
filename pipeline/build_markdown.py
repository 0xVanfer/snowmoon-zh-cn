#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把「结构骨架 + 中文片段」组装成 Markdown（逐章）与全书单文件。

用法:
    python3 pipeline/build_markdown.py            # 组装全部已译章节
    python3 pipeline/build_markdown.py 1 2 3      # 只重建这几章的逐章文件

注意：参数只影响**逐章文件**；全书单文件 book/snowmoon-zh.md 始终由全部可用译文重建，
否则一次定向重建就会把已入库的整本书截断成所选章节（历史 bug）。
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
KNOWN_TAGS = {"br", "c", "f", "b", "i", "e", "code", "a", "sup", "sub", "u", "small", "mark"}


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


def mini_to_md(text: str, escape: bool = True) -> str:
    """mini-markup → Markdown / 内联 HTML。

    escape=False 用于「骨架本身就是原始 HTML」的块（device-view 面板等）：
    Markdown 转义序列在 raw HTML block 里不会被解释，加了反斜杠反而会显示成字面量。

    [用户请求] 中文不用斜体：本书是中文成品，`<e>`/`<i>`（原文着重）一律落成加粗 `**`，
    不再输出 `*…*`。见 docs/style-guide.md §2。
    """
    out: list[str] = []
    pos = 0
    links: list[str] = []

    def text_out(s: str) -> str:
        return MD_ESCAPE.sub(r"\\\1", s) if escape else s

    for m in TAG_RE.finditer(text):
        out.append(text_out(text[pos:m.start()]))
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
    out.append(text_out(text[pos:]))
    return "".join(out)


def expand(skeleton: str, segs: dict[str, str], escape: bool = True) -> str:
    """替换 {{S:id}}；片段缺失直接报错，绝不静默留空。"""
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in segs:
            raise SystemExit(f"骨架引用了不存在的片段 {key}（译文与骨架不同步）")
        return mini_to_md(segs[key], escape)

    return PLACEHOLDER_RE.sub(sub, skeleton)


def block_ids(blk: dict) -> list[str]:
    return [m.group(1) for m in PLACEHOLDER_RE.finditer("".join(blk.get("segs", [])))]


def clean_ws(s: str) -> str:
    s = re.sub(r"[ \t]+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def discover_chapters() -> list[int]:
    """全部可能有译文的章号（骨架 ∪ 译文）。

    [P1] 原本是两处独立的 `range(1, 33)`：第 33 章即便有了骨架和译文也会被静默丢弃。
    """
    found = set()
    for pat, rx in ((CHAP_DIR, r"chapter-(\d+)\.json$"), (ZH_DIR, r"chapter-(\d+)\.zh\.json$")):
        for p in pat.glob("chapter-*.json"):
            m = re.search(rx, p.name)
            if m:
                found.add(int(m.group(1)))
    return sorted(found)


def build_chapter(ch: int, segs: dict[str, str], img_prefix: str = "../images/") -> str | None:
    cf = CHAP_DIR / f"chapter-{ch:02d}.json"
    if not cf.exists():
        return None
    data = json.loads(cf.read_text(encoding="utf-8"))
    # 全量核对骨架与译文是否同步：章标题/卷首日期等块不经过 expand，
    # 只靠 expand 兜底会让这类 id 失配静默留空。
    ids = set(PLACEHOLDER_RE.findall(json.dumps(data, ensure_ascii=False)))
    missing = sorted(ids - set(segs))
    if missing:
        raise SystemExit(f"chapter-{ch:02d}: 骨架引用的片段在译文中缺失 {missing[:4]}")
    # [P1] 缺清单原本 exit 0 并把图注退化成占位串，而 build_site 对同一缺失直接抛
    # SystemExit —— 三个产物互相矛盾。清单是图注与 alt 的唯一来源，缺了就必须停住。
    if not FIG_MANIFEST.exists():
        raise SystemExit(
            f"缺少插图清单 {FIG_MANIFEST.relative_to(ROOT)}："
            f"没有它就只能生成「插图 chapter-NN-fig-MM」这类占位串。"
            f"请先跑 make_figures.py apply。")
    man = json.loads(FIG_MANIFEST.read_text(encoding="utf-8"))
    captions: dict[str, str] = {k: v.get("caption", "") for k, v in man.items()}
    parts: list[str] = []
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind == "title":
            parts.append(f"# 第{cn_num(ch)}章\n")
        elif kind in ("dateline-open", "scene-break"):
            vals = [segs[i] for i in block_ids(blk) if segs.get(i)]
            line = " · ".join(vals)
            cls = "dateline" if kind == "dateline-open" else "scene-break"
            if kind == "scene-break":
                parts.append("---\n")
            parts.append(f'<p class="{cls}">{mini_to_md(line, escape=False)}</p>\n')
        elif kind == "rule":
            parts.append("---\n")
        elif kind == "figure":
            figs = blk.get("figures", [])
            for f in figs:
                name = f[:-4]
                cap = captions.get(name, "")
                alt = (cap or f"插图 {name}").replace("]", "］").replace("\n", " ")
                parts.append(f"![{alt}]({img_prefix}{f})\n")
            if blk.get("skeleton"):
                parts.append(expand(blk["skeleton"], segs, escape=False) + "\n")
        elif kind in ("p",):
            html = expand(blk.get("skeleton", ""), segs, escape=True)
            inner = re.sub(r"^<p>|</p>$", "", html)
            parts.append(inner + "\n")
        else:
            # panel / center / list / quote 等：骨架本身就是原始 HTML
            parts.append(expand(blk.get("skeleton", ""), segs, escape=False) + "\n")
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
    all_chapters = discover_chapters()
    todo = sorted({int(x) for x in sys.argv[1:]}) or all_chapters

    # ---- 计划阶段：先把每一章渲染成字符串，**全部成功**才开始写盘 ----
    # [P1] 原来是在校验循环里边渲染边写：第 12 章缺片段而 exit 1 时，
    # 前 11 章的 .md 已经落盘，工作区留下半新半旧的产物。
    # 与 build_site 的 plan/emit 一致：先全部渲染成功，再统一写。
    pages: list[tuple[int, str]] = []
    for ch in todo:
        segs = load_segs(ch)
        if not segs:
            print(f"skip ch{ch:02d}（无译文）")
            continue
        md = build_chapter(ch, segs, "../images/")
        if md is None:
            print(f"skip ch{ch:02d}（无骨架）")
            continue
        pages.append((ch, md + "\n"))

    # 全书单文件：始终用「全部可用译文」重建，定向参数不影响它
    # [P1] 缺骨架曾经只 print 一句「skip（无骨架）」就 exit 0，把整本书静默截成 31 章，
    # 而 build_site 对同一缺失直接抛 FileNotFoundError —— 三个产物互相矛盾。
    # 译文在、骨架不在，是「半成品」而不是「这一章不存在」，必须停住。
    no_skeleton = [ch for ch in all_chapters
                   if load_segs(ch) and not (CHAP_DIR / f"chapter-{ch:02d}.json").exists()]
    if no_skeleton:
        raise SystemExit(
            f"以下章有译文但缺少骨架，拒绝组装（否则整本书会被静默截短）：{no_skeleton}")
    available = [ch for ch in all_chapters
                 if (CHAP_DIR / f"chapter-{ch:02d}.json").exists() and load_segs(ch)]
    if not available:
        raise SystemExit("没有任何可用译文，未生成全书 Markdown")
    toc = [f"- [第{cn_num(ch)}章](chapters/chapter-{ch:02d}.md)" for ch in available]
    book = FRONT + "\n".join(toc) + "\n\n"
    for ch in available:
        book += "\n\n---\n\n" + build_chapter(ch, load_segs(ch), "images/") + "\n"

    # ---- 落盘阶段：到这里所有校验都已经过了 ----
    BOOK_CH.mkdir(parents=True, exist_ok=True)
    for ch, md in pages:
        (BOOK_CH / f"chapter-{ch:02d}.md").write_text(md, encoding="utf-8")
    (BOOK / "snowmoon-zh.md").write_text(book, encoding="utf-8")
    print(f"组装完成：逐章 {len(pages)} 个文件 + 全书 {len(available)} 章 → book/")


if __name__ == "__main__":
    main()
