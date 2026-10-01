#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""插图校验：中文版 SVG 与原图的等价性检查。

检查项：
  1. XML 合法；
  2. 根元素属性（width/height/viewBox/xmlns/preserveAspectRatio/transform/opacity/style）与原文一致；
  3. **带父链的**元素结构一致（`svg/g[2]/text[3]`）——扁平前序列表看不出重父化；
  4. 逐元素比对几何/外观属性（transform、d、points、坐标、尺寸、fill、stroke、opacity…）；
     <text> 另比对 x/y/anchor/weight/family，font-size 允许 ±20% 微调；
  5. 整图数字序列一致，且图例「标签 + 数值」的配对与顺序和原文一致；
  6. 数字、符号、虚构语言文本必须原样；其余文本必须已含中文；
  7. 不得残留成串英文单词（缩略语白名单除外）。

用法: python3 pipeline/validate_svg.py [原始文件 中文文件]
       省略参数时逐个比对 sources/work/figures/*.svg ↔ book/images/*.svg（缺一张即失败）
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "work" / "figures"
BOOK = ROOT / "book" / "images"

ALLOW_LATIN = {"AI", "API", "GPH", "DU", "VNU", "GUI", "XOR", "TAU", "SHI", "GEI", "LLM", "US", "OK",
               "PM", "KAG", "ZIU", "UVC", "FA", "LE", "BI", "ZE", "HA", "CO", "GU", "MU", "AGI", "ID",
               "URL", "PDF", "HTML", "CSS", "SVG", "B", "KB", "MB", "GB", "Hz", "kg", "km", "cm", "mm"}

# [P0] 逐元素比对的几何/外观属性。翻译只该改 <text> 的字，换个写法挪个位置都不行。
# 少任何一个，下面这些注入都会「56 对图，失败 0」地通过：
#   根 <svg transform="translate(9999,9999)"> → 整幅图移出画布渲染成空白
#   <g transform="translate(0,-3000)">         → 同上
#   全部 <path d="M0 0"> / fill=#ff0000       → 图形消失、配色全变
GEOMETRY_ATTRS = (
    "transform", "opacity", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
    "stroke-opacity", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
    "d", "points", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "dx", "dy", "offset", "text-anchor",
    "font-weight", "display", "visibility", "clip-path", "mask", "offset-x", "offset-y",
    "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "patternUnits",
    "marker-end", "marker-start", "letter-spacing", "word-spacing", "text-decoration",
)
# font-size / font-family 不在上表：<text> 循环里对它们另有专门规则
# （font-size 允许 ±20%，中文字形宽窄不同，模型会为「彼得斯维尔」把 10 调成 9）。
# 在这里逐字比会把那条有意的容差变成死条款。


def grouped(paths):
    """只取 <g> 分组及其直属 <text>，路径形式 svg/g[4]/g[2]。

    图表里「标签 + 数值」总是同一个 <g> 下的两个相邻 <text>，
    配对关系就编码在这个分组里。
    """
    out = []
    for path, el in paths:
        if strip_ns(el.tag) != "g":
            continue
        kids = [c for c in el if strip_ns(c.tag) == "text"]
        if kids:
            out.append((path, kids))
    return out


def attr_style(style: str) -> dict[str, str]:
    """把内联 style 拆成声明字典，排序无关地比较。"""
    out = {}
    for decl in (style or "").split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _load_vocab() -> set[str]:
    """泽国语（Dzegoban）罗马字词表：从 locked 片段自动统计而来。"""
    vf = ROOT / "sources" / "work" / "conlang_vocab.json"
    if vf.exists():
        return set(json.loads(vf.read_text(encoding="utf-8")))
    return set()


CONLANG_VOCAB = _load_vocab()
MATH_VARS = {"x", "y", "z", "n", "k", "p", "t", "a", "b", "c", "d", "r", "e", "m", "q", "s", "w", "v"}
# 整个 <text> 就是一个数（图表里的数值节点）
NUMBER_ONLY_RE = re.compile(r"^-?\d+(?:\.\d+)?\s*%?$")


def walk_path(el, path="", out=None):
    """带父链的扁平列表：每项是 (父链路径, 元素)。

    [P0] 原先的 walk() 产出**扁平前序**，`<g>X</g>` → `<g/>X` 的序列完全相同
    （53 == 53），重父化后看不出任何区别——图形被挪到别的分组里，图就错了。
    改成 `svg/g[2]/text[3]` 形式，父链不同即报错。
    """
    if out is None:
        out = []
    name = strip_ns(el.tag)
    here = f"{path}/{name}"
    out.append((here, el))
    counts: dict[str, int] = {}
    for c in el:
        cn = strip_ns(c.tag)
        counts[cn] = counts.get(cn, 0) + 1
        walk_path(c, f"{here}[{counts[cn]}]", out)
    return out


def is_numberish(s: str) -> bool:
    if re.fullmatch(r"[\s\d\.\,\:\;\-\+\(\)\[\]%°×÷=<>&/\\|'\"！？，。…—·、￥$€£#@*^~_\u00a0\u2192\u2713]*", s):
        return True
    if re.fullmatch(r"(0x)?[0-9a-fA-F]{4,}\.{0,3}", s):  # 哈希 / 十六进制
        return True
    if re.search(r"\d", s) and re.fullmatch(r"[\d\s\.\,\%]*[A-Za-z]{1,3}[\d\s\.\,\%]*", s):
        return True  # 222nm、5kg 之类（必须含数字，避免把 Mov 这类三字母人名当单位）
    return False


def is_conlang(s: str) -> bool:
    toks = re.findall(r"[a-z]+", s.lower())
    if not toks:
        return False
    return all(t in CONLANG_VOCAB or t in MATH_VARS for t in toks)


def has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", s))


def validate(src_path: Path, zh_path: Path) -> list[str]:
    errs: list[str] = []
    try:
        src = ET.fromstring(src_path.read_text(encoding="utf-8"))
    except ET.ParseError as e:
        return [f"原图 XML 解析失败: {e}"]
    try:
        zh = ET.fromstring(zh_path.read_text(encoding="utf-8"))
    except ET.ParseError as e:
        return [f"中文图 XML 解析失败: {e}"]

    for attr in ("width", "height", "viewBox", "xmlns", "preserveAspectRatio"):
        if (src.get(attr) or "") != (zh.get(attr) or ""):
            errs.append(f"根属性 {attr} 不一致: {src.get(attr)!r} → {zh.get(attr)!r}")
    # [P0] 根 <svg> 的 transform 此前完全不查：加一条 translate(9999,9999)
    # 就能把整幅图移出画布、渲染成空白，而校验报「56 对图，失败 0」。
    for attr in ("transform", "opacity", "style"):
        if (src.get(attr) or "") != (zh.get(attr) or ""):
            errs.append(f"根属性 {attr} 变化: {src.get(attr)!r} → {zh.get(attr)!r}")
    if strip_ns(src.tag) != strip_ns(zh.tag):
        errs.append(f"根标签不一致: {src.tag} → {zh.tag}")

    # [P0] 结构比对改为带父链；几何属性逐元素比对。
    # 原先只比 <text> 的 x/y/anchor/fill/weight/transform，
    # <rect>/<line>/<path>/<circle>/<polygon> 的 d/points/坐标/尺寸/stroke/opacity 一个都不看。
    ps, pz = walk_path(src), walk_path(zh)
    if len(ps) != len(pz):
        errs.append(f"元素序列不一致: 原 {len(ps)} 个 / 中 {len(pz)} 个")
    else:
        for (pa, a), (pb, b) in zip(ps, pz):
            if pa != pb:
                errs.append(f"元素层级不一致: {pa} → {pb}")
                break
            for attr in GEOMETRY_ATTRS:
                av, bv = (a.get(attr) or ""), (b.get(attr) or "")
                if attr == "style":
                    # style 里塞了几何/颜色，逐个声明拆开比，避免"换个写法"绕过
                    if attr_style(av) != attr_style(bv):
                        errs.append(f"{pa}: style 变化 {attr_style(av)!r} → {attr_style(bv)!r}")
                    continue
                if av != bv:
                    errs.append(f"{pa}: 属性 {attr} 变化 {av!r} → {bv!r}")

    st = [e for e in ps if strip_ns(e[1].tag) == "text"]
    zt = [e for e in pz if strip_ns(e[1].tag) == "text"]
    if len(st) != len(zt):
        errs.append(f"text 数量不一致: {len(st)} → {len(zt)}")
        return errs

    for a, b in zip(st, zt):
        ea, eb = a[1], b[1]
        for attr in ("x", "y", "text-anchor", "fill", "font-weight", "transform", "font-family", "opacity"):
            if (ea.get(attr) or "") != (eb.get(attr) or ""):
                errs.append(f'text "{ea.text}": 属性 {attr} 变化 '
                            f'{ea.get(attr)!r} → {eb.get(attr)!r}')
        try:
            fs_a, fs_b = float(ea.get("font-size") or 0), float(eb.get("font-size") or 0)
            if fs_a and abs(fs_b - fs_a) / fs_a > 0.2:
                errs.append(f'text "{ea.text}": font-size 变化过大 {fs_a} → {fs_b}')
        except ValueError:
            pass
        ta = "".join(ea.itertext()).strip()
        tb = "".join(eb.itertext()).strip()
        if is_numberish(ta) or is_conlang(ta):
            if ta != tb:
                errs.append(f"数字/符号/虚构语言被改动: {ta!r} → {tb!r}")
            continue
        if not has_cjk(tb):
            errs.append(f"未译成中文: {ta!r} → {tb!r}")
            continue
        # [P0] 数字/虚构语言以外的原文，此前只检查「译文含中文」，
        # **从不与原文比对**：把「毫无信心(39%)」与「很有信心(12%)」原地对调
        # （只换字、数值留在原位），图表结论完全反转而校验照样通过。
        # 这里比对两边的数值：任何一段数字都必须原样出现在译文里。
        na = re.findall(r"-?\d+(?:\.\d+)?%?", ta)
        nb = re.findall(r"-?\d+(?:\.\d+)?%?", tb)
        if na and na != nb:
            errs.append(f"图中数值被改动（结论可能反转）: {ta!r} → {tb!r}")
        # 图中标注残留英文：中文与英文混排也要拦（旧版要求「去掉英文后完全没有中文」，
        # 那个条件恒不成立，等于这条检查从来没生效过）。
        leftover = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", tb) if w not in ALLOW_LATIN]
        if leftover:
            errs.append(f"残留英文: {ta!r} → {tb!r}（{', '.join(leftover[:3])}）")

    # [P0] 整幅图的数字序列必须逐一对应。
    # 逐个 <text> 比不出来：图表常把标签和数值拆成相邻的两个节点
    # （「毫无信心」+「39%」），标签对调后每个节点自身都「合法」。
    # 把全文所有数字按出现顺序拉成一条序列再比，对调就一定会暴露。
    def numbers(paths):
        out = []
        for _, el in paths:
            out.extend(re.findall(r"-?\d+(?:\.\d+)?%?", "".join(el.itertext())))
        return out

    nums_a, nums_b = numbers(ps), numbers(pz)
    if nums_a != nums_b:
        errs.append(f"整图数字序列不一致（图表结论可能反转）: "
                    f"原 {nums_a[:10]} → 中 {nums_b[:10]}")

    # [P0] 标签与数值的**配对**也必须一致。
    # 整图数字序列相同并不够：图表常把「毫无信心」和「39%」拆成相邻两个 <text>，
    # 把两个标签对调后每个数字都还在原位，整图序列完全相同 —— 结论却整个反了。
    # 这里按「同一个 <g> 分组里的文字」配对：组内文字顺序必须一一对应。
    for (ga, ea), (gb, eb) in zip(grouped(ps), grouped(pz)):
        if ga != gb:
            errs.append(f"分组层级不一致: {ga} → {gb}")
            break
        ta_list = ["".join(e.itertext()).strip() for e in ea]
        tb_list = ["".join(e.itertext()).strip() for e in eb]
        # 数值必须落在同一位置（配对错位 = 结论错）
        na = [i for i, t in enumerate(ta_list) if NUMBER_ONLY_RE.match(t)]
        nb = [i for i, t in enumerate(tb_list) if NUMBER_ONLY_RE.match(t)]
        if na != nb:
            errs.append(f"{ga}: 数值与标签的配对错位 {ta_list} → {tb_list}")

    # [P0] 图例里的「标签 + 数值」必须与原文一一对应。
    # 上面两条都挡不住这一种：把两个 <g> 的**文字**对调、几何完全不动，
    # 数字序列不变、分组结构不变、配对位置也不变 —— 但「毫无信心 39%」
    # 变成了「毫无信心 12%」，图表结论整个反转。
    # 唯一的可靠依据是原文：同一个数值在原文里配的是另一个词。
    # 用「数值 → 原文标签」建索引，再逐个核对译文标签对应的原文标签是否同源。
    def legend_pairs(paths):
        """返回 [(值, 标签)]，按文档顺序。"""
        out = []
        for path, kids in grouped(paths):
            texts = ["".join(k.itertext()).strip() for k in kids]
            num = next((t for t in texts if NUMBER_ONLY_RE.match(t)), None)
            lab = next((t for t in texts if t != num), None)
            if num and lab:
                out.append((path, num, lab))
        return out

    la, lb = legend_pairs(ps), legend_pairs(pz)
    if len(la) == len(lb) and la:
        # 原文与译文的图例顺序必须一致：图例重排会让每个数值配上错误的标签，
        # 而结构、几何、整图数字序列全都看不出问题。
        if [n for _, n, _ in la] != [n for _, n, _ in lb]:
            errs.append("图例顺序与原文不一致（数值与标签的对应关系可能整体错位）")
        # 每个图例分组的标签必须译成中文：标签留在原位、数值被换过来时，
        # 译文标签会退化成原文英文，看起来「没动过」实则整体错位。
        for (pa, na_, la_), (pb, nb_, lb_) in zip(la, lb):
            if la_ == lb_ and not has_cjk(lb_) and has_cjk(la_):
                errs.append(f"{pa}: 图例标签疑似被换回原文（数值配对可能错位）: {lb_!r}")
    return errs


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if any(a.startswith("--") for a in sys.argv[1:]):
        raise SystemExit("未知参数（本脚本只接受「原始文件 中文文件」两个位置参数）")
    missing: list[str] = []
    if len(args) == 2:
        pairs = [(Path(args[0]), Path(args[1]))]
    elif len(args) == 1:
        raise SystemExit("用法: validate_svg.py [原始文件 中文文件]")
    else:
        pairs = []
        for f in sorted(SRC.glob("*.svg")):
            b = BOOK / f.name
            if b.exists():
                pairs.append((f, b))
            else:
                missing.append(f.name)
    bad = 0
    for s, z in pairs:
        errs = validate(s, z)
        if errs:
            bad += 1
            print(f"FAIL {s.name} ({len(errs)})")
            for e in errs[:6]:
                print("   -", e)
        else:
            print(f"OK   {s.name}")
    for name in missing:
        bad += 1
        print(f"FAIL {name}: 缺少中文版 book/images/{name}")
    if not pairs and not missing:
        print("没有任何可校验的图（sources/work/figures 为空？）")
        sys.exit(1)
    print(f"{len(pairs)} 对图，失败 {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
