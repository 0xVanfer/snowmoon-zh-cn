#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""译文自检：结构一致性校验。

对照 sources/work/segments/chapter-NN.src.json 与 translations/zh/chapter-NN.zh.json：
  1. 片段 id 集合与顺序完全一致；
  2. locked 片段必须逐字不变（虚构语言不得翻译）；
  3. mini-markup 标签序列（含属性）完全一致，杜绝丢标签/改样式/丢颜色；
  4. 不得残留非法标签、未转义的尖括号、{{S:}} 占位符；
  5. 目标文本必须含中文（除 locked、纯数字/符号/URL/界面 token 外）。

用法: python3 pipeline/validate_translation.py [章节号...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "sources" / "work" / "segments"
ZH = ROOT / "translations" / "zh"

TAG_RE = re.compile(r"<(/?)([a-z]+)([^>]*?)(/?)>")
ALLOWED = {"c", "b", "i", "e", "sup", "sub", "code", "a", "br", "f", "u", "small", "mark"}


def tag_seq(s: str) -> list[str]:
    out = []
    for m in TAG_RE.finditer(s):
        closing, name, attrs, selfclose = m.groups()
        out.append(f"{'/' if closing else ''}{name}{attrs.strip()}{'/' if selfclose else ''}")
    return out


def strip_tags(s: str) -> str:
    return TAG_RE.sub("", s)


def check(chapter: int) -> list[str]:
    errs: list[str] = []
    src_p = WORK / f"chapter-{chapter:02d}.src.json"
    zh_p = ZH / f"chapter-{chapter:02d}.zh.json"
    if not zh_p.exists():
        return [f"缺失译文文件 {zh_p.relative_to(ROOT)}"]
    src = json.loads(src_p.read_text(encoding="utf-8"))["segments"]
    try:
        data = json.loads(zh_p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]
    zh = data.get("segments") or []
    if [s["id"] for s in src] != [s.get("id") for s in zh]:
        errs.append("片段 id 序列与原文不一致")
        miss = [s["id"] for s in src if s["id"] not in {z.get("id") for z in zh}]
        extra = [z.get("id") for z in zh if z.get("id") not in {s["id"] for s in src}]
        if miss:
            errs.append(f"  缺失 {len(miss)} 条: {miss[:8]}")
        if extra:
            errs.append(f"  多余 {len(extra)} 条: {extra[:8]}")
        return errs
    for s, z in zip(src, zh):
        sid = s["id"]
        tz = z.get("text")
        if not isinstance(tz, str):
            errs.append(f"{sid}: text 不是字符串")
            continue
        if s["locked"]:
            if tz != s["text"]:
                errs.append(f"{sid}: locked 片段被改动（虚构语言必须原样保留）")
            continue
        st, zt = tag_seq(s["text"]), tag_seq(tz)
        if st != zt:
            errs.append(f"{sid}: 标签序列不一致\n    原文 {st}\n    译文 {zt}")
        if "{{S:" in tz:
            errs.append(f"{sid}: 残留占位符 {{{{S:…}}}}")
        body = strip_tags(tz)
        if "<" in body or ">" in body:
            errs.append(f"{sid}: 残留未转义尖括号: {body[:80]}")
        for name in set(re.findall(r"<([a-z]+)", tz)):
            if name not in ALLOWED:
                errs.append(f"{sid}: 非法标签 <{name}>")
        if not re.search(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]", body):
            # 允许纯数字 / 符号 / URL / 代码 / 界面英文 token
            if re.search(r"[A-Za-z]{3,}", body) and not re.fullmatch(
                    r"[\s0-9A-Za-z\.\-_/:#%+*×xX°·,()\[\]{}<>=~^|\\'\"!?]+", body):
                errs.append(f"{sid}: 疑似未翻译（无中文）: {body[:90]}")
        if re.search(r"\s{2,}", body) and not re.search(r"<br/>", tz):
            errs.append(f"{sid}: 出现连续空格: {body[:60]}")
    return errs


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    bad = 0
    for ch in todo:
        errs = check(ch)
        if errs:
            bad += 1
            print(f"FAIL ch{ch:02d} ({len(errs)} 处)")
            for e in errs[:12]:
                print("   -", e)
        else:
            print(f"OK   ch{ch:02d}")
    print("失败章节数:", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
