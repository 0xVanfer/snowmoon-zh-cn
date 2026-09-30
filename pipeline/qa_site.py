#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""阅读站点自检（结构，不校验文字）：页面齐全、占位符清空、双语两栏在位、
布局容器（flex/grid，如投票刻度条）子项与原文一一对应、链接与插图可解析。

用法: python3 pipeline/qa_site.py
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "en" / "html"
SITE = ROOT / "book" / "site"
REPO_URL = "https://github.com/0xVanfer/snowmoon-zh-cn"
SITE_URL = "https://snowmoon.vanfer.tech/"
EMAIL = "vanfer@vanfer.tech"
CHAPTERS = list(range(1, 33))

FLEX_RE = re.compile(r'<div[^>]*style="[^"]*(?:display\s*:\s*(?:flex|grid)|justify-content)[^"]*"[^>]*>(.*?)</div>', re.S | re.I)
CHILD_RE = re.compile(r"<(span|b|i|em|strong|code|a|sup|sub)\b[^>]*>(.*?)</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def norm(s: str) -> str:
    s = htmlmod.unescape(TAG_RE.sub("", s))
    return re.sub(r"\s+", "", s)


def flex_rows(text: str) -> Counter:
    """抽取页面里所有布局容器的「直接子元素文字序列」。"""
    rows: Counter = Counter()
    for m in FLEX_RE.finditer(text):
        kids = [norm(k) for _, k in CHILD_RE.findall(m.group(1))]
        if kids:
            rows[tuple(kids)] += 1
    return rows


def main() -> None:
    problems: list[str] = []
    if not (SITE / "index.html").exists():
        print("站点未构建：book/site/index.html 不存在")
        sys.exit(1)

    # 1) 文件齐全
    need = ["index.html", "toc.html", "assets/style.css", "assets/reader.js", ".nojekyll"]
    for f in need:
        if not (SITE / f).exists():
            problems.append(f"缺少 {f}")
    pages = {}
    for ch in CHAPTERS:
        p = SITE / "read" / f"chapter-{ch:02d}.html"
        if not p.exists():
            problems.append(f"缺少 read/chapter-{ch:02d}.html")
            continue
        pages[ch] = p.read_text(encoding="utf-8")
    index = (SITE / "index.html").read_text(encoding="utf-8")
    toc = (SITE / "toc.html").read_text(encoding="utf-8")

    # 2) 占位符与模板残留
    for name, text in [("index.html", index), ("toc.html", toc)] + \
                      [(f"read/chapter-{c:02d}.html", t) for c, t in pages.items()]:
        left = re.findall(r"\{\{[^}]*\}\}", text)
        if left:
            problems.append(f"{name}: 残留占位符 {sorted(set(left))[:5]}")

    # 3) 主页必须有仓库地址与联系方式
    for token, label in ((REPO_URL, "GitHub 仓库地址"), (EMAIL, "联系邮箱"), (SITE_URL, "站点地址")):
        if token not in index:
            problems.append(f"index.html 缺少{label}：{token}")

    # 4) 每章双语两栏在位
    for ch, text in pages.items():
        for attr in ('data-lang="zh"', 'data-lang="en"'):
            if attr not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 {attr} 正文栏")
        for cid in ('id="pane-zh"', 'id="pane-en"', 'id="nav-prev"', 'id="nav-next"',
                    'id="drawer-toc"', 'id="settings-panel"', 'id="progress-bar"'):
            if cid not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 {cid}")
        if len(text) < 20000:
            problems.append(f"chapter-{ch:02d}: 页面过小（{len(text)} 字节），正文可能没注入")

    # 5) 布局容器（flex/grid）结构保真：原文里每个布局容器的子项序列都要在成品里出现
    for ch, text in pages.items():
        src_text = (SRC / f"chapter-{ch}.html").read_text(encoding="utf-8")
        want, got = flex_rows(src_text), flex_rows(text)
        for row, n in want.items():
            if got.get(row, 0) < n:
                problems.append(
                    f"chapter-{ch:02d}: 布局容器子项丢失/错位 {list(row)}（原文 {n} 处，成品 {got.get(row, 0)} 处）")

    # 6) 站内链接与图片可解析
    for name, text, base in [("index.html", index, SITE), ("toc.html", toc, SITE)] + \
                            [(f"read/chapter-{c:02d}.html", t, SITE / "read") for c, t in pages.items()]:
        for attr, url in re.findall(r'(href|src)="([^"#?]+)"', text):
            if re.match(r"^(https?:|mailto:|data:|//)", url):
                continue
            if not (base / url).exists():
                problems.append(f"{name}: {attr}=\"{url}\" 指向的文件不存在")

    # 7) 插图引用完整
    imgs = {p.name for p in (SITE / "assets" / "images").glob("*.svg")}
    if len(imgs) != 56:
        problems.append(f"assets/images 下插图数量不是 56：{len(imgs)}")
    refs: Counter = Counter()
    for text in pages.values():
        refs.update(re.findall(r"images/([A-Za-z0-9._-]+\.svg)", text))
    missing = sorted(set(refs) - imgs)
    if missing:
        problems.append(f"引用了不存在的插图：{missing[:4]}")
    unused = sorted(imgs - set(refs))
    if unused:
        problems.append(f"有插图未被任何页面引用：{unused[:4]}")

    # 8) 无 JS 降级：样式必须保证中文单栏可读、交互控件不出现
    css = ""
    for f in ("assets/style.css", "assets/overrides.css"):
        if (SITE / f).exists():
            css += (SITE / f).read_text(encoding="utf-8")
    for sel in ("html:not([data-js]) #pane-zh", "html:not([data-js]) #pane-en",
                "html:not([data-js]) #lang-tabs", "html:not([data-js]) .js-only"):
        if sel not in css:
            problems.append(f"缺无 JS 降级规则：{sel}")
    for name, text in [("index.html", index)] + [(f"read/chapter-{c:02d}.html", t) for c, t in pages.items()]:
        if re.search(r"<html[^>]*\sdata-js", text):
            problems.append(f"{name}: 静态 HTML 里出现了 data-js（应由 JS 运行时添加）")

    # 9) 目录条目
    if toc.count("data-chapter=") < 32:
        problems.append(f"toc.html 目录条目不足 32：{toc.count('data-chapter=')}")
    for ch in CHAPTERS:
        if f'href="read/chapter-{ch:02d}.html"' not in toc:
            problems.append(f"toc.html 缺少第 {ch} 章链接")

    if problems:
        print(f"发现 {len(problems)} 处问题：")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"OK：{len(pages)} 章 + 主页 + 目录，结构自检通过（含布局容器子项保真）")


if __name__ == "__main__":
    main()
