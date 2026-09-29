#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""抽取自检：把抽取结果还原成纯文本，与原始 HTML 的纯文本逐章比对，确保无漏字、无重复。

用法:
    python3 pipeline/verify_extract.py            # 全量
    python3 pipeline/verify_extract.py 1 2 3      # 指定章
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "sources" / "work"
SRC = ROOT / "sources" / "en" / "html"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\{\{S:[^}]+\}\}", " ", s)
    s = re.sub(r"\s+", "", s)
    return s


def strip_tags_mini(s: str) -> str:
    s = re.sub(r"<br/>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return s


def slice_page(raw: str) -> str:
    i = raw.find('<div class="document-page">')
    j = raw.rfind("</div>")
    body = raw[i:j + 6]
    body = re.sub(r"<nav.*?</nav>", " ", body, flags=re.S)
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    # SVG 内部文字由图像流水线单独处理，这里排除
    body = re.sub(r"<svg.*?</svg>", " ", body, flags=re.S)
    # 解码实体（&#8594; &nbsp; 等），与抽取侧（HTMLParser 已解码）对齐
    body = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), body)
    body = body.replace("&nbsp;", "\u00a0").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return body


def original_text(chapter: int) -> str:
    return norm(slice_page((SRC / f"chapter-{chapter}.html").read_text(encoding="utf-8")))


def extracted_text(chapter: int) -> str:
    data = json.loads((WORK / "chapters" / f"chapter-{chapter:02d}.json").read_text(encoding="utf-8"))
    segmap = {s["id"]: s["text"] for s in json.loads(
        (WORK / "segments" / f"chapter-{chapter:02d}.src.json").read_text(encoding="utf-8"))["segments"]}
    parts: list[str] = []
    for b in data["blocks"]:
        kind = b.get("kind")
        if kind in ("dateline-open", "scene-break"):
            parts.append(b.get("place") or "")
            parts.append(b.get("date") or "")
            continue
        if kind == "figure":
            if b.get("skeleton"):
                parts.append(b["skeleton"])
            continue
        parts.append(b.get("skeleton", ""))
    joined = " ".join(parts)
    joined = re.sub(r"\{\{S:([^}]+)\}\}", lambda m: segmap.get(m.group(1), ""), joined)
    return norm(joined)


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    bad = 0
    for ch in todo:
        a = original_text(ch)
        b = extracted_text(ch)
        # 字符集合对比：找出抽取里缺失/多出的片段
        missing = []
        i = 0
        while i < len(a):
            if a[i:i + 20] and a[i:i + 20] not in b and a[i:i + 12] not in b and a[i:i + 8] not in b:
                missing.append(a[max(0, i - 30):i + 30])
                i += 40
            else:
                i += 1
        extra = []
        i = 0
        while i < len(b):
            if b[i:i + 20] and b[i:i + 20] not in a and b[i:i + 12] not in a and b[i:i + 8] not in a:
                extra.append(b[max(0, i - 30):i + 30])
                i += 40
            else:
                i += 1
        status = "OK " if not missing and not extra else "DIFF"
        if missing or extra:
            bad += 1
        print(f"{status} ch{ch:02d} orig={len(a):6d} extr={len(b):6d} missing={len(missing)} extra={len(extra)}")
        for m in missing[:5]:
            print(f"    MISSING …{m}…")
        for m in extra[:5]:
            print(f"    EXTRA   …{m}…")
    print("chapters with differences:", bad)


if __name__ == "__main__":
    main()
