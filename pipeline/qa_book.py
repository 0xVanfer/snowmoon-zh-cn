#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""成品自检：对组装后的 Markdown 做书级体检。

检查项：
  1. 未替换占位符 / 抽取残留（{{S:、<f>、<c st=）；
  2. 章数、插图引用**路径可解析**（相对各自 md 文件所在目录）、无未引用插图；
  3. 中文体例（半角标点、省略号、空格体例）；
  4. 游离的 Markdown 转义反斜杠（原始 HTML 块里不该出现）。

用法: python3 pipeline/qa_book.py
注意：book/snowmoon-zh.html 并不存在（没有任何脚本生产它），因此这里不再假装校验 HTML。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "book"
MD = BOOK / "snowmoon-zh.md"
CHAPTERS = BOOK / "chapters"
IMAGES = BOOK / "images"

IMG_REF_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def main() -> None:
    problems: list[str] = []
    if not MD.exists():
        print("缺少 book/snowmoon-zh.md")
        sys.exit(1)
    md = MD.read_text(encoding="utf-8")

    # 1) 未替换占位符 / 抽取残留
    for pat, label in ((r"\{\{S:", "未替换的片段占位符"), (r"\{\{", "残留 {{ 占位符"),
                       (r"<f>|</f>", "未转换的 <f> 标签"), (r"<c st=", "未转换的 <c> 标签")):
        n = len(re.findall(pat, md))
        if n:
            problems.append(f"{label}: {n} 处")

    # 2) 章节与插图
    chapters = re.findall(r"^# 第(.+?)章$", md, re.M)
    if len(chapters) != 32:
        problems.append(f"章数不是 32：{len(chapters)}")

    md_files = [MD] + sorted(CHAPTERS.glob("chapter-*.md"))
    refs: set[str] = set()
    for f in md_files:
        for r in IMG_REF_RE.findall(f.read_text(encoding="utf-8")):
            refs.add(Path(r).name)
            if not (f.parent / r).exists():
                problems.append(f"{f.relative_to(ROOT)}: 插图路径无法解析 {r}")
    have = {p.name for p in IMAGES.glob("*.svg")}
    missing = sorted(refs - have)
    if missing:
        problems.append(f"引用了不存在的插图 {len(missing)} 个：{missing[:4]}")
    unused = sorted(have - refs)
    if unused:
        problems.append(f"有插图未被引用 {len(unused)} 个：{unused[:4]}")

    # 3) 中文体例：直接检查译文片段（去掉 mini-markup 标签后的可见文字）
    seg_texts = []
    for f in sorted((ROOT / "translations" / "zh").glob("chapter-*.zh.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for s_ in data["segments"]:
            t = re.sub(r"<[^>]+>", "", s_["text"])
            if t.strip():
                seg_texts.append((f.stem, s_["id"], t))
    checks = {
        "半角逗号紧跟汉字": r"[\u4e00-\u9fff],",
        "半角句号紧跟汉字": r"[\u4e00-\u9fff]\.",
        "半角问号紧跟汉字": r"[\u4e00-\u9fff]\?",
        "半角叹号紧跟汉字": r"[\u4e00-\u9fff]!",
        "半角分号紧跟汉字": r"[\u4e00-\u9fff];",
        "半角冒号紧跟汉字": r"[\u4e00-\u9fff]:",
        "英文省略号": r"(?<![\d.])\.\.\.(?![\d.])",
        "连续空格": r"[^\s] {2,}[^\s]",
        "数字与汉字间有空格": r"[\u4e00-\u9fff] \d+(?![\dA-Za-z.])|(?<![\dA-Za-z.\-_/%])\d+ [\u4e00-\u9fff]",
        "拉丁词与汉字间缺空格": r"[\u4e00-\u9fff][A-Za-z]{2,}|[A-Za-z][A-Za-z0-9.\-_/%]*[\u4e00-\u9fff]",
    }
    for label, pat in checks.items():
        hits = []
        for c, i, t in seg_texts:
            for m in re.finditer(pat, t):
                hits.append((c, i, t[max(0, m.start() - 20):m.end() + 20]))
        if hits:
            problems.append(f"{label}: {len(hits)} 处（示例 {hits[0][0]} {hits[0][1]} …{hits[0][2]}…）")

    # 4) 游离的 Markdown 转义反斜杠：raw HTML 块里不会被解释，会原样显示
    stray = [(i + 1, ln.strip()[:100]) for i, ln in enumerate(md.splitlines())
             if re.search(r"\\[\[\]\*_`]", ln)]
    if stray:
        problems.append(f"Markdown 里残留转义反斜杠 {len(stray)} 行"
                        f"（示例第 {stray[0][0]} 行）")

    visible = sum(len(t) for _, _, t in seg_texts)
    print(f"Markdown：{len(chapters)} 章、{len(refs)} 张插图；译文可见文字约 {visible/1000:.0f} 千字符")
    if problems:
        print("\n发现以下问题：")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("\n书级自检通过")


if __name__ == "__main__":
    main()
