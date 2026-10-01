#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""生成泽国语（Dzegoban）罗马字词表，供插图校验判断「哪些文字不该翻译」。

来源（并集）：
  1. 抽取阶段标记为 locked 的片段（dz-line / pre 等）；
  2. 原始 HTML 中 Chorus 字体的 span；
  3. 播报体（PA GU … SO … BI … ZE … HA …）——源文里**没有**标 locked，
     全靠 1/2 时 TAU/SO/BI/ZE/HA/SHI/LE/ZIU 这些音节一个都进不了词表，
     「泽国语必须原样保留」的反向校验对它们完全失效；
  4. 原始 SVG 中「整条 text 全小写且每个词不超过 4 字母」的文字（英语标签总会出现长词，
     泽国语音节全部 ≤4 字母）。

用法: python3 pipeline/build_conlang_vocab.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "sources" / "work" / "segments"
FIG = ROOT / "sources" / "work" / "figures"
SRC = ROOT / "sources" / "en" / "html"
OUT = ROOT / "sources" / "work" / "conlang_vocab.json"

# 泽国语音节上限。PA/SO 这类播报词与 bau/dzu 一样短；超过 4 字母基本是英语。
SYLLABLE_MAX = 4
# 播报体判据之一：整条去标签正文里的罗马字必须全是大写。
# 「WHAT?」「JUST IN:」也满足，靠下面「多数词已是已知音节」这条排除。
# 刻意**不**依赖 st="color:oklch(...)"：c27-s0114（… HUI ZIU FA!）根本没有 <c> 标签。


def _segments() -> list[dict]:
    out: list[dict] = []
    for f in sorted(SEG.glob("chapter-*.src.json")):
        out.extend(json.loads(f.read_text(encoding="utf-8"))["segments"])
    return out


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def locked_syllables() -> set[str]:
    """来源 1 + 2：可靠种子词表。"""
    syl: set[str] = set()
    for s in _segments():
        if s.get("locked"):
            syl.update(re.findall(r"[a-z]+", _plain(s["text"])))
    for f in sorted(SRC.glob("chapter-*.html")):
        for m in re.finditer(r'<span style="[^"]*Chorus[^"]*">([^<]*)</span>',
                             f.read_text(encoding="utf-8")):
            syl.update(re.findall(r"[a-z]+", m.group(1)))
    return syl


def collect_chant_syllables(syl: set[str]) -> set[str]:
    """来源 3：从播报体片段里增量采集音节，直到不动点。

    单靠「全大写 + 每词 ≤4 字母」会把 CO 2 / PM2.5 / WHAT? / JUST IN: / MUN GUI 1842
    一并收进来，这些是英语缩写和英语词，进了词表就会让「英文残留」检查漏报。
    因此再加一条硬约束：**该片段去重后的音节里至少有一半已经是已知音节**，
    且至少 2 个音节（单音节的 TEI 70000 / CO 2 / PM2.5 / WHAT? 全部因此被排除）。

    一次扫描收不齐——「SO ... BI ... ZE ... HA ...」单独出现时四个音节都还陌生，
    要等「LE MU GEI TAU FA」把 le/tau 收进来之后它才过半——所以必须迭代到不动点。
    """
    candidates: list[set[str]] = []
    for s in _segments():
        words = re.findall(r"[A-Za-z]+", _plain(s.get("text", "")))
        if not words or not all(w.isupper() and len(w) <= SYLLABLE_MAX for w in words):
            continue
        uniq = {w.lower() for w in words}
        if len(uniq) >= 2:
            candidates.append(uniq)

    added: set[str] = set()
    # 候选集合有限，每轮只增不减，round 上限仅作死循环兜底
    for _ in range(len(candidates) + 1):
        new: set[str] = set()
        for uniq in candidates:
            if len([w for w in uniq if w in syl]) * 2 < len(uniq):
                continue
            new.update(w for w in uniq if w not in syl)
        if not new:
            break
        syl.update(new)
        added.update(new)
    return added


def main() -> None:
    vocab = locked_syllables()
    added = collect_chant_syllables(vocab)
    print(f"种子词表 {len(vocab)} 词；播报体新增 {len(added)} 词: {sorted(added)}")
    for f in sorted(FIG.glob("*.svg")):
        for m in re.finditer(r"<text[^>]*>(.*?)</text>", f.read_text(encoding="utf-8"), re.S):
            t = _plain(m.group(1)).strip()
            if not t or t != t.lower():
                continue
            words = re.findall(r"[a-z]+", t)
            # 多词条：每个词 ≤4 字母（英语标签总会出现长词）
            # 单词条：仅 ≤3 字母（bau/dzu/ja/lui 等泽国语音节；care/testing 这类英文词排除）
            if (len(words) >= 2 and all(len(w) <= 4 for w in words)) or \
               (len(words) == 1 and len(words[0]) <= 3):
                vocab.update(words)
    OUT.write_text(json.dumps(sorted(vocab), ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"泽国语词表 {len(vocab)} 词 → {OUT.relative_to(ROOT)}")
    print("较长词:", sorted([w for w in vocab if len(w) == 4]))


if __name__ == "__main__":
    main()

