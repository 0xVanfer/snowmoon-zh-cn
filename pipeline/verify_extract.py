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
from extract import slice_document_page, HTML_ONLY_TAGS  # noqa: E402

# 「只属于 HTML、绝不该出现在 <svg> 内部」的标签集合。复用 extract 的常量是为了让两边
# 对「什么算 breakout 点」保持同一份口径（切片函数已经是共用的）；共享的是**规格常量**，
# 不是判定算法——算法在下面 strip_elements 里独立实现，避免共同错误互相抵消。
# 已核对：56 张插图内不含任何 HTML-only 标签，所以按此规则收尾不会误伤图内元素。
HTML_ONLY_TOKEN_RE = re.compile(
    r"</?(?:" + "|".join(sorted(HTML_ONLY_TAGS)) + r")\b", re.I)

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

    第 30 章上游有两个未闭合的 <svg>：正则非贪婪匹配会从它一路吃到后面某个 </svg>，
    把中间整段正文一并删掉，于是校验器自己制造出「原文缺失」。这里只删配平的，
    未配平的按 HTML 的 breakout 规则收尾——到下一个「只属于 HTML 的标签」为止
    （与 extract.py 的 in_foreign/break_out_of_svg 同一条规则，但在文本层**独立**实现：
    校验器与被校验对象共用实现会把共同错误抵消），并把个数报给上层留痕。
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
            # 未闭合的 <svg> 按 breakout 规则收尾：连同它内部的内容一起**丢弃**
            # （剥离就是剥离——留着会让图里的 <text> 图注混进原文，制造假的 MISSING）。
            nxt = HTML_ONLY_TOKEN_RE.search(text, m.end())
            if not nxt:
                break
            i = nxt.start()
            continue
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


def discover_chapters() -> list[int]:
    """章号由磁盘上真实存在的上游 HTML 决定，而不是写死的 1..32。"""
    return sorted({int(m.group(1))
                   for m in (re.fullmatch(r"chapter-(\d+)\.html", p.name)
                             for p in SRC.glob("chapter-*.html"))
                   if m})


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or discover_chapters()
    if not SRC.exists():
        print("sources/en/html 不存在（上游原文不入库），跳过抽取还原比对")
        return
    bad = 0
    warned = 0
    for ch in todo:
        a, unbalanced = original_text(ch)
        if unbalanced:
            # [P0] 此前这里 continue 却不计入 bad，脚本照常 exit 0 —— 「本章从未比对过」
            # 被印成了一条无害的 WARN；后来改成一计入失败，又让第 30 章永远无法被比对。
            # 两条路都不对：真正的问题是「校验器自己没法安全地切这一章」。
            # 现在 strip_elements 已按 breakout 规则收尾，切得掉了，所以本章照常比对——
            # 上游缺 </svg> 是**上游的缺陷**，要留痕；但抽取侧已按 HTML 规则正确收口，
            # 若它真的吞了正文，比对会立刻报 missing。判据从「有没有比对过」换成
            # 「比对结果有没有差异」，这一章才真的进入了闸门覆盖范围。
            print(f"WARN ch{ch:02d}: 上游有 {unbalanced} 个未闭合的 <svg>（上游缺 </svg>）；"
                  f"抽取侧按 HTML breakout 规则已收口，本章**照常**做还原比对", file=sys.stderr)
            warned += 1
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
    if warned:
        print(f"其中 {warned} 章上游 <svg> 未闭合（已按 breakout 规则处理并完成比对）",
              file=sys.stderr)
    print("chapters with differences:", bad)
    # 这个脚本必须能失败：否则它只是一份日志，不是一道闸门
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
