#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""成品自检：对组装后的 Markdown / HTML 做书级体检。

用法: python3 pipeline/qa_book.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "book"
MD = BOOK / "snowmoon-zh.md"
HTML = BOOK / "snowmoon-zh.html"
IMAGES = BOOK / "images"


def main() -> None:
    problems: list[str] = []
    md = MD.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8") if HTML.exists() else ""

    # 1) 未替换占位符 / 抽取残留
    for pat, label in ((r"\{\{S:", "未替换的片段占位符"), (r"\{\{", "残留 {{ 占位符"),
                       (r"<f>|</f>", "未转换的 <f> 标签"), (r"<c st=", "未转换的 <c> 标签")):
        n = len(re.findall(pat, md))
        if n:
            problems.append(f"{label}: {n} 处")

    # 2) 章节与插图完整性
    chapters = re.findall(r"^# 第(.+?)章$", md, re.M)
    if len(chapters) != 32:
        problems.append(f"章数不是 32：{len(chapters)}")
    refs = set(re.findall(r"\]\(\.\./images/([^)]+)\)", md)) | set(re.findall(r"\]\(images/([^)]+)\)", md))
    have = {p.name for p in IMAGES.glob("*.svg")}
    missing = sorted(refs - have)
    if missing:
        problems.append(f"引用了不存在的插图 {len(missing)} 个：{missing[:4]}")
    unused = sorted(have - refs)
    if unused:
        problems.append(f"有插图未被引用 {len(unused)} 个：{unused[:4]}")

    # 3) 中文体例
    # 3) 中文体例：直接检查译文片段（去掉 mini-markup 标签后的可见文字），
    #    比检查组装后的 Markdown 准确——后者会因标签边界产生大量误报。
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
        hits = [(c, i, t[max(0, m.start() - 20):m.end() + 20])
                for c, i, t in seg_texts for m in [re.search(pat, t)] if m]
        if hits:
            problems.append(f"{label}: {len(hits)} 处（示例 {hits[0][0]} {hits[0][1]} …{hits[0][2]}…）")

    # 4) HTML 一致性
    if html:
        for pat, label in ((r"\{\{S:", "HTML 残留占位符"),):
            if re.search(pat, html):
                problems.append(label)
        n_p = len(re.findall(r"<p[\s>]", html))
        if n_p != html.count("</p>"):
            problems.append(f"HTML 中 <p> 不配对：{n_p} vs {html.count('</p>')}")
        n_div = len(re.findall(r"<div[\s>]", html))
        if n_div != html.count("</div>"):
            problems.append(f"HTML 中 <div> 不配对：{n_div} vs {html.count('</div>')}")
        img = re.findall(r'<img src="images/([^"]+)"', html)
        miss = sorted(set(img) - have)
        if miss:
            problems.append(f"HTML 引用了不存在的插图：{miss[:4]}")
        print(f"HTML：{len(img)} 张插图、{len(html)/1024:.0f} KB")

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
