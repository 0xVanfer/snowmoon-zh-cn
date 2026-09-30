#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""插图校验：中文版 SVG 与原图的等价性检查。

检查项：
  1. XML 合法；
  2. 根元素属性（width/height/viewBox/xmlns）与原文一致；
  3. 元素标签序列（含层级顺序）完全一致——不得增删图形元素；
  4. <text> 数量一致，位置/对齐/颜色属性不变，font-size 允许 ±20% 微调；
  5. 数字、符号、虚构语言文本必须原样；其余文本必须已含中文；
  6. 不得残留成串英文单词（缩略语白名单除外）。

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


def walk(el, out):
    out.append(el)
    for c in el:
        walk(c, out)
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

    for attr in ("width", "height", "viewBox"):
        if (src.get(attr) or "") != (zh.get(attr) or ""):
            errs.append(f"根属性 {attr} 不一致: {src.get(attr)!r} → {zh.get(attr)!r}")
    if strip_ns(src.tag) != strip_ns(zh.tag):
        errs.append(f"根标签不一致: {src.tag} → {zh.tag}")

    ws, wz = [], []
    walk(src, ws)
    walk(zh, wz)
    ts = [strip_ns(e.tag) for e in ws]
    tz = [strip_ns(e.tag) for e in wz]
    if ts != tz:
        errs.append(f"元素序列不一致: 原 {len(ts)} 个 / 中 {len(tz)} 个")
        for i, (a, b) in enumerate(zip(ts, tz)):
            if a != b:
                errs.append(f"  第 {i} 个元素: {a} → {b}")
                break

    st = [e for e in ws if strip_ns(e.tag) == "text"]
    zt = [e for e in wz if strip_ns(e.tag) == "text"]
    if len(st) != len(zt):
        errs.append(f"text 数量不一致: {len(st)} → {len(zt)}")
        return errs

    for a, b in zip(st, zt):
        for attr in ("x", "y", "text-anchor", "fill", "font-weight", "transform"):
            if (a.get(attr) or "") != (b.get(attr) or ""):
                errs.append(f'text "{a.text}": 属性 {attr} 变化 {a.get(attr)!r} → {b.get(attr)!r}')
        try:
            fs_a, fs_b = float(a.get("font-size") or 0), float(b.get("font-size") or 0)
            if fs_a and abs(fs_b - fs_a) / fs_a > 0.2:
                errs.append(f'text "{a.text}": font-size 变化过大 {fs_a} → {fs_b}')
        except ValueError:
            pass
        ta = "".join(a.itertext()).strip()
        tb = "".join(b.itertext()).strip()
        if is_numberish(ta) or is_conlang(ta):
            if ta != tb:
                errs.append(f"数字/符号/虚构语言被改动: {ta!r} → {tb!r}")
            continue
        if not has_cjk(tb):
            errs.append(f"未译成中文: {ta!r} → {tb!r}")
            continue
        # 图中标注残留英文：中文与英文混排也要拦（旧版要求「去掉英文后完全没有中文」，
        # 那个条件恒不成立，等于这条检查从来没生效过）。
        leftover = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", tb) if w not in ALLOW_LATIN]
        if leftover:
            errs.append(f"残留英文: {ta!r} → {tb!r}（{', '.join(leftover[:3])}）")
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
