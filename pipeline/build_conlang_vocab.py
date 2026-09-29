#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""生成泽国语（Dzegoban）罗马字词表，供插图校验判断「哪些文字不该翻译」。

来源（并集）：
  1. 抽取阶段标记为 locked 的片段（dz-line / pre 等）；
  2. 原始 HTML 中 Chorus 字体的 span；
  3. 原始 SVG 中「整条 text 全小写且每个词不超过 4 字母」的文字（英语标签总会出现长词，
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


def main() -> None:
    vocab: set[str] = set()
    for f in SEG.glob("chapter-*.src.json"):
        for s in json.loads(f.read_text(encoding="utf-8"))["segments"]:
            if s.get("locked"):
                vocab.update(re.findall(r"[a-z]+", re.sub(r"<[^>]+>", " ", s["text"])))
    for f in SRC.glob("chapter-*.html"):
        html = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<span style="[^"]*Chorus[^"]*">([^<]*)</span>', html):
            vocab.update(re.findall(r"[a-z]+", m.group(1)))
    for f in FIG.glob("*.svg"):
        svg = f.read_text(encoding="utf-8")
        for m in re.finditer(r"<text[^>]*>(.*?)</text>", svg, re.S):
            t = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
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
