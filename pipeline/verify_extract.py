#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""抽取自检：把抽取结果还原成纯文本，与原始 HTML 的纯文本逐章比对，确保无漏字、无重复。

与 extract.py 共用同一个切片函数（曾各自演化导致两边口径不一致）。

已知的**有意差异**（不算问题）：
  * dateline 的 `<span class="sep">·</span>` 分隔号由构建侧重新拼入；
  * 字符实体在两侧都做一次解码，避免 `>` 与 `&gt;` 被误判为缺失。

用法:
    python3 pipeline/verify_extract.py            # 全量
    python3 pipeline/verify_extract.py 1 2 3      # 指定章
需要上游原文（sources/en/html），缺失时直接跳过（该目录不入库）。
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract import slice_document_page  # noqa: E402

WORK = ROOT / "sources" / "work"
SRC = ROOT / "sources" / "en" / "html"


def decode_entities(s: str) -> str:
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    s = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), s)
    return (s.replace("&nbsp;", "\u00a0").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u00a0", " ")
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\{\{S:[^}]+\}\}", " ", s)
    s = re.sub(r"\s+", "", s)
    return s


def strip_elements(text: str, tag: str) -> tuple[str, int]:
    """剥离标签配平的 <tag>…</tag>，返回 (结果, 未配平个数)。

    第 30 章上游有未闭合的 <svg>：正则非贪婪匹配会从它一路吃到后面某个 </svg>，
    把中间整段正文一并删掉，于是校验器自己制造出「原文缺失」。这里只删配平的，
    未配平的报出来交给上层，而不是悄悄污染比对结果。
    """
    out: list[str] = []
    i = 0
    unbalanced = 0
    open_re = re.compile(rf"<{tag}\b[^>]*>", re.I)
    tok_re = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
    while True:
        m = open_re.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        depth, j = 1, m.end()
        while depth and j < len(text):
            t = tok_re.search(text, j)
            if not t:
                break
            depth += -1 if t.group(1) else 1
            j = t.end()
        if depth:
            unbalanced += 1
            out.append(text[m.start():])
            break
        i = j
    return "".join(out), unbalanced


def slice_page(raw: str) -> tuple[str, int]:
    body = slice_document_page(raw)
    # nav 先剥（导航图标本身就是 svg），再剥配平的 svg
    body = re.sub(r"<nav\b.*?</nav>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<script\b.*?</script>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<style\b.*?</style>", " ", body, flags=re.S | re.I)
    body, unbalanced = strip_elements(body, "svg")
    # dateline 分隔号：抽取层有意丢弃，构建侧会重新插入
    body = re.sub(r'<span[^>]*class="[^"]*\bsep\b[^"]*"[^>]*>.*?</span>', " ", body, flags=re.S | re.I)
    return decode_entities(body), unbalanced


def original_text(chapter: int) -> tuple[str, int]:
    body, unbalanced = slice_page((SRC / f"chapter-{chapter}.html").read_text(encoding="utf-8"))
    return norm(body), unbalanced


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
    return norm(decode_entities(joined))


def regions_of(a: str, b: str, width: int = 40) -> list[tuple[int, int]]:
    """找出 a 中不在 b 里的片段，合并相邻命中后再计数（不再用 i+=40 跳过窗口）。"""
    hits = []
    i = 0
    while i < len(a):
        if a[i:i + 8] and a[i:i + 20] not in b and a[i:i + 12] not in b and a[i:i + 8] not in b:
            hits.append(i)
            i += 8
        else:
            i += 1
    merged: list[list[int]] = []
    for h in hits:
        if merged and h - merged[-1][1] <= width:
            merged[-1][1] = h
        else:
            merged.append([h, h])
    return [(s, e) for s, e in merged]


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    if not SRC.exists():
        print("sources/en/html 不存在（上游原文不入库），跳过抽取还原比对")
        return
    bad = 0
    for ch in todo:
        a, unbalanced = original_text(ch)
        if unbalanced:
            print(f"WARN ch{ch:02d}: 上游有 {unbalanced} 个未配平的 <svg>，本章跳过还原比对"
                  f"（插图已由 validate_svg.py 单独校验）")
            continue
        b = extracted_text(ch)
        missing = regions_of(a, b)
        extra = regions_of(b, a)
        status = "OK " if not missing and not extra else "DIFF"
        if missing or extra:
            bad += 1
        print(f"{status} ch{ch:02d} orig={len(a):6d} extr={len(b):6d} "
              f"missing={len(missing)} extra={len(extra)}")
        for s, e in missing[:5]:
            print(f"    MISSING …{a[max(0, s - 20):e + 20]}…")
        for s, e in extra[:5]:
            print(f"    EXTRA   …{b[max(0, s - 20):e + 20]}…")
    print("chapters with differences:", bad)
    # 这个脚本必须能失败：否则它只是一份日志，不是一道闸门
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
