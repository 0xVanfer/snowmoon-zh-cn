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
import html
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
LINE_INDEX = ROOT / "pipeline" / "line_index.json"

TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")
KNOWN_TAGS = {"br", "c", "f", "b", "i", "e", "code", "a", "sup", "sub", "u", "small", "mark", "tn"}

# 当前章的译者注 {片段id: 注内容}，由 load_tnotes() 在渲染每章前就地替换。
# mini_to_md 是模块级函数，注内容只能经这里传给 <tn> 的 title 兜底。
_TNOTES: dict[str, str] = {}


def load_tnotes(ch: int) -> dict[str, str]:
    """读一章的 translator_notes，做成 {id: note}。

    缺 `note` 或 id 不是字符串的条目直接报错：注是要给读者看的，
    悄悄丢掉一条比构建失败更难发现。
    """
    p = ZH_DIR / f"chapter-{ch:02d}.zh.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8")).get("translator_notes") or []
    out: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) \
                or not isinstance(item.get("note"), str):
            raise SystemExit(
                f"chapter-{ch:02d}.zh.json: translator_notes 条目必须是 "
                f'{{"id": str, "note": str}}，收到 {item!r}')
        out[item["id"]] = item["note"]
    return out


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
        elif name == "tn":
            # [译者注] Markdown 产物没有 JS 气泡，改用 title 兜底：多数 Markdown
            # 阅读器（GitHub、VS Code、Typora）都会把 title 显示成悬停提示。
            # 章末再补一份完整注脚，保证纯文本读者也读得到。
            if closing:
                out.append("</span>")
            else:
                nm = re.search(r'note="([^"]*)"', attrs)
                note = _TNOTES.get(nm.group(1), "") if nm else ""
                tip = html.escape(f"译注：{note}", quote=True) if note else "译注"
                out.append(f'<span class="tnote" title="{tip}">')
    out.append(text_out(text[pos:]))
    return "".join(out)


def tnote_block(notes: dict[str, str]) -> str:
    """章末译注块。气泡只在站点里有，纯 Markdown 读者靠这一段。"""
    if not notes:
        return ""
    rows = "\n".join(f"> **译注（{nid}）**　{text}" for nid, text in notes.items())
    return f"\n### 译注\n\n{rows}\n"


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


def resolve_line_index(text: str, probes: list[tuple[str, str]], ch: int) -> dict[str, tuple[int, int]]:
    """把每个块的「首行探针」定位到最终文本的行号，得到 {片段 id: (起行, 止行)}。

    [为什么不往正文里插标记]  `docs/explainer/` 里 497 处 `chapter-NN.md:行号`
    引用是按**当前**行号写死的，而本函数末尾的 `clean_ws()` 会折叠空行并 strip。
    只要在 parts 里插一行标记，其后所有块的行号全部前移，497 条引用同时错位——
    而且错位后每一行仍然「存在且非空」，逐条核对也查不出来。
    所以这里只做只读定位：产物字节一个都不动。
    """
    out: dict[str, tuple[int, int]] = {}
    cursor = 0
    starts: list[int] = []
    for seg, probe in probes:
        pos = text.find(probe, cursor)
        if pos < 0:
            raise SystemExit(
                f"chapter-{ch:02d}: 段落探针在产物里定位不到 {probe[:40]!r}；"
                f"行号索引会失准，docs/explainer 的 497 处引用将全部错位")
        starts.append(text.count("\n", 0, pos) + 1)
        cursor = pos + len(probe)
    # 块 i 拥有 [starts[i], starts[i+1]-1]；最后一块一直拥有到文末
    bounds = starts + [text.count("\n") + 2]
    for i, (seg, _probe) in enumerate(probes):
        out[seg] = (starts[i], bounds[i + 1])
    return out


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


def build_chapter(ch: int, segs: dict[str, str], img_prefix: str = "../images/",
                  line_index: dict[str, tuple[int, int]] | None = None) -> str | None:
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
    probes: list[tuple[str, str]] = []

    def emit(text: str, seg_ids: list[str]) -> None:
        """追加一块产物；行号索引模式下顺带记下它的首行探针与归属片段。

        产物字符串与改造前**逐字节一致**——探针只用于事后只读定位，不写回正文。
        """
        parts.append(text)
        if line_index is None or not seg_ids:
            return
        first = next((ln for ln in text.split("\n") if ln.strip()), "")
        if first:
            probes.append((seg_ids[0], first))

    for blk in data["blocks"]:
        kind = blk.get("kind")
        blk_ids = block_ids(blk)
        if kind == "title":
            emit(f"# 第{cn_num(ch)}章\n", [])
        elif kind in ("dateline-open", "scene-break"):
            vals = [segs[i] for i in blk_ids if segs.get(i)]
            line = " · ".join(vals)
            cls = "dateline" if kind == "dateline-open" else "scene-break"
            if kind == "scene-break":
                emit("---\n", [])
            emit(f'<p class="{cls}">{mini_to_md(line, escape=False)}</p>\n', blk_ids)
        elif kind == "rule":
            emit("---\n", [])
        elif kind == "figure":
            for f in blk.get("figures", []):
                name = f[:-4]
                cap = captions.get(name, "")
                alt = (cap or f"插图 {name}").replace("]", "］").replace("\n", " ")
                emit(f"![{alt}]({img_prefix}{f})\n", [])
            if blk.get("skeleton"):
                emit(expand(blk["skeleton"], segs, escape=False) + "\n", blk_ids)
        elif kind in ("p",):
            rendered = expand(blk.get("skeleton", ""), segs, escape=True)
            inner = re.sub(r"^<p>|</p>$", "", rendered)
            emit(inner + "\n", blk_ids)
        else:
            # panel / center / list / quote 等：骨架本身就是原始 HTML
            emit(expand(blk.get("skeleton", ""), segs, escape=False) + "\n", blk_ids)
    # 章末译注：正文里的 <span class="tnote"> 只有 title 兜底，
    # 这里补一份可读的完整注脚，纯文本/不支持悬停的阅读器也能拿到内容。
    emit(tnote_block(_TNOTES), [])
    text = clean_ws("\n".join(parts))
    if line_index is not None:
        line_index.update(resolve_line_index(text, probes, ch))
    return text


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
        _TNOTES.clear()
        _TNOTES.update(load_tnotes(ch))
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
        _TNOTES.clear()
        _TNOTES.update(load_tnotes(ch))
        book += "\n\n---\n\n" + build_chapter(ch, load_segs(ch), "images/") + "\n"

    # ---- 行号索引：{章: {片段 id: (起行, 止行)}} ----
    # docs/explainer 的 497 处 `chapter-NN.md:行号` 引用要靠它换算成站点锚点。
    # 走**全部可用章**而不是 todo：定向重建只给某几章时，索引不能变成残缺的
    # ——残缺的索引会让 build_site 生成指向不存在段落的链接，而构建照样成功。
    line_index: dict[int, dict[str, tuple[int, int]]] = {}
    for ch in available:
        _TNOTES.clear()
        _TNOTES.update(load_tnotes(ch))
        per: dict[str, tuple[int, int]] = {}
        build_chapter(ch, load_segs(ch), "../images/", line_index=per)
        line_index[ch] = per

    # ---- 落盘阶段：到这里所有校验都已经过了 ----
    BOOK_CH.mkdir(parents=True, exist_ok=True)
    for ch, md in pages:
        (BOOK_CH / f"chapter-{ch:02d}.md").write_text(md, encoding="utf-8")
    (BOOK / "snowmoon-zh.md").write_text(book, encoding="utf-8")
    LINE_INDEX.write_text(json.dumps(
        {"_comment": "行号索引，由 build_markdown.py 生成：{章: {片段 id: [起行, 止行]}}。"
                     "docs/explainer 的 `chapter-NN.md:行号` 引用靠它换算成站点锚点，"
                     "请勿手改。",
         "chapters": {str(ch): {seg: [a, b] for seg, (a, b) in per.items()}
                      for ch, per in sorted(line_index.items())}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"组装完成：逐章 {len(pages)} 个文件 + 全书 {len(available)} 章 → book/"
          f"；行号索引 {sum(len(p) for p in line_index.values())} 条 → "
          f"{LINE_INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
