#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""阅读站点自检（结构，不校验文字）。

检查项：
  1. 页面齐全、占位符清空、双语两栏与交互控件在位；
  2. **布局容器保真**：内联 flex/grid/justify-content 的容器的直接子项序列，逐条与原文比对
     （任意标签，且按配平标签取内容，不再只认 <div> + 非贪婪到第一个 </div>）；
  3. **结构元素计数**：原文的表格/行/单元格/引用/列表项/终端面板数量不得在成品里减少；
  4. **中文栏非空**：中文正文长度不得相对原文塌陷（防止「片段被静默替换成空串」）；
  5. 站内链接与图片可解析、插图引用完整；
  6. 无 JS 降级规则在位；
  7. 目录条目与「实际发布的章」一致；
  8. assets 与 pipeline/site 同步（防止提交陈旧构建产物）。

上游英文原文（sources/en/html）不入库，缺失时第 2/3/4 项自动跳过并提示。
用法: python3 pipeline/qa_site.py
"""
from __future__ import annotations

import html as htmlmod
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources" / "en" / "html"
SITE = ROOT / "book" / "site"
FRONT = ROOT / "pipeline" / "site"
REPO_URL = "https://github.com/0xVanfer/snowmoon-zh-cn"
SITE_URL = "https://snowmoon.vanfer.tech/"
EMAIL = "vanfer@vanfer.tech"
CHAPTERS = list(range(1, 33))

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "param", "source", "track", "wbr", "path", "rect", "line", "circle", "polygon",
             "polyline", "ellipse", "use", "stop"}
TAGSCAN = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>")
TAG_RE = re.compile(r"<[^>]+>")
FLEX_STYLE_RE = re.compile(r"display\s*:\s*(?:flex|grid)|justify-content", re.I)
# 结构标记：这些标签数量由抽取层保留，翻译不可能增删，因此可以逐章比对
STRUCT_TAGS = ("table", "tr", "td", "th", "blockquote", "li")
DEVICE_RE = re.compile(r'class="[^"]*device-view', re.I)


def norm(s: str) -> str:
    s = htmlmod.unescape(TAG_RE.sub("", s))
    return re.sub(r"\s+", "", s)


def balanced_element(text: str, start: int) -> str | None:
    """从 start 处取出一个标签配平的元素（含自身）。"""
    m = re.match(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>", text[start:])
    if not m:
        return None
    tag = m.group(1).lower()
    if tag in VOID_TAGS or m.group(0).rstrip().endswith("/>"):
        return m.group(0)
    depth = 0
    for t in re.finditer(rf"<(/?){re.escape(tag)}\b[^>]*>", text[start:], re.I):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return text[start:start + t.end()]
    return None


def direct_children(inner: str) -> list[str]:
    out: list[str] = []
    depth = 0
    start = None
    for m in TAGSCAN.finditer(inner):
        closing, name, attrs = m.group(1), m.group(2).lower(), m.group(3)
        selfclose = attrs.rstrip().endswith("/") or name in VOID_TAGS
        if closing:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(inner[start:m.end()])
                start = None
            continue
        if depth == 0:
            if selfclose:
                out.append(m.group(0))
            else:
                depth, start = 1, m.start()
        elif not selfclose:
            depth += 1
    return out


def flex_rows(text: str) -> Counter:
    """页面里所有布局容器的「直接子元素文字序列」。"""
    rows: Counter = Counter()
    for m in re.finditer(r"<[a-zA-Z][a-zA-Z0-9]*\b[^>]*style=\"[^\"]*\"[^>]*>", text):
        if not FLEX_STYLE_RE.search(m.group(0)):
            continue
        el = balanced_element(text, m.start())
        if not el:
            continue
        inner = el[el.index(">") + 1: el.rindex("</")] if "</" in el else ""
        kids = [norm(k) for k in direct_children(inner)]
        kids = [k for k in kids if k]
        if kids:
            rows[tuple(kids)] += 1
    return rows


def struct_counts(text: str) -> Counter:
    c: Counter = Counter()
    for tag in STRUCT_TAGS:
        c[tag] = len(re.findall(rf"<{tag}\b", text, re.I))
    return c


def chapter_figures(ch: int) -> tuple[int, int, int]:
    """骨架里 figure 块数、插图总数、以及带残留正文的 figure 块数。

    带 SVG 的终端面板会输出 <figure>；若该面板除 SVG 外还有可读内容（表格兜底等），
    同一块还会再输出一个 .device-view 残留层——比对面板数量时必须算上这一层。
    """
    import json
    p = ROOT / "sources" / "work" / "chapters" / f"chapter-{ch:02d}.json"
    if not p.exists():
        return 0, 0, 0
    blocks = json.loads(p.read_text(encoding="utf-8"))["blocks"]
    figs = [b for b in blocks if b.get("kind") == "figure"]
    leftover = sum(1 for b in figs if b.get("skeleton"))
    return len(figs), sum(len(b.get("figures", [])) for b in figs), leftover


def strip_noise(text: str) -> str:
    for tag in ("nav", "script", "style"):
        text = re.sub(rf"<{tag}\b.*?</{tag}>", " ", text, flags=re.S | re.I)
    return text


def pane_text(page: str, lang: str) -> str:
    """取某一语言栏的 HTML 片段（#pane-zh 到 #pane-en 之间）。"""
    a = page.find(f'id="pane-{lang}"')
    if a < 0:
        return ""
    b = page.find('id="pane-en"', a) if lang == "zh" else page.find("</main>", a)
    return page[a:b if b > a else len(page)]


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

    # 4) 每章双语两栏 + 交互控件
    for ch, text in pages.items():
        for attr in ('data-lang="zh"', 'data-lang="en"'):
            if attr not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 {attr} 正文栏")
        for cid in ('id="pane-zh"', 'id="pane-en"', 'id="nav-prev"', 'id="nav-next"',
                    'id="drawer-toc"', 'id="settings-panel"', 'id="progress-bar"'):
            if cid not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 {cid}")

    # 5~7) 需要上游原文的检查
    if not SRC.exists():
        print("提示：sources/en/html 不存在（上游原文不入库），"
              "跳过布局容器/结构计数/中文栏长度三项检查")
    else:
        for ch, text in pages.items():
            src_file = SRC / f"chapter-{ch}.html"
            if not src_file.exists():
                problems.append(f"chapter-{ch:02d}: 缺少上游原文 {src_file.name}，无法比对结构")
                continue
            src_text = strip_noise(src_file.read_text(encoding="utf-8"))
            # 6.1 布局容器子项序列
            want, got = flex_rows(src_text), flex_rows(text)
            for row, n in want.items():
                if got.get(row, 0) < n:
                    problems.append(
                        f"chapter-{ch:02d}: 布局容器子项丢失/错位 {list(row)}"
                        f"（原文 {n} 处，成品 {got.get(row, 0)} 处）")
            # 6.2 结构元素计数不得减少
            sc, bc = struct_counts(src_text), struct_counts(pane_text(text, "en"))
            for tag, n in sc.items():
                if n and bc.get(tag, 0) < n:
                    problems.append(
                        f"chapter-{ch:02d}: <{tag}> 数量减少（原文 {n}，成品英文栏 {bc.get(tag, 0)}）")
            # 6.2b 终端面板：带 SVG 的会变成 <figure>，其余仍保留 .device-view
            fig_blocks, fig_total, fig_leftover = chapter_figures(ch)
            src_dv = len(DEVICE_RE.findall(src_text))
            out_dv = len(DEVICE_RE.findall(pane_text(text, "en")))
            out_fig = len(re.findall(r'<figure class="fig"', pane_text(text, "en"), re.I))
            if src_dv != out_dv + fig_blocks - fig_leftover:
                problems.append(
                    f"chapter-{ch:02d}: 终端面板数量不符（原文 {src_dv} 个，成品 {out_dv} 个 "
                    f".device-view + {fig_blocks} 个 figure 块 − {fig_leftover} 个残留层）")
            if out_fig != fig_total:
                problems.append(
                    f"chapter-{ch:02d}: 插图数量不符（骨架 {fig_total} 张，成品英文栏 {out_fig} 张）")
            # 6.3 中文栏不得塌陷
            zh_len = len(norm(pane_text(text, "zh")))
            en_len = len(norm(pane_text(text, "en")))
            if en_len and zh_len < en_len * 0.25:
                problems.append(
                    f"chapter-{ch:02d}: 中文栏疑似缺失（中文 {zh_len} 字符 / 英文 {en_len} 字符）")
            if zh_len < 2000:
                problems.append(f"chapter-{ch:02d}: 中文栏过短（{zh_len} 字符），正文可能没注入")

    # 8) 站内链接与图片可解析
    for name, text, base in [("index.html", index, SITE), ("toc.html", toc, SITE)] + \
                            [(f"read/chapter-{c:02d}.html", t, SITE / "read") for c, t in pages.items()]:
        for attr, url in re.findall(r'(href|src)="([^"#?]+)"', text):
            if re.match(r"^(https?:|mailto:|data:|//)", url):
                continue
            if not (base / url).exists():
                problems.append(f"{name}: {attr}=\"{url}\" 指向的文件不存在")

    # 9) 插图引用完整
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

    # 10) 无 JS 降级
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
        if 'href="assets/overrides.css"' not in text and 'href="../assets/overrides.css"' not in text:
            problems.append(f"{name}: 没有引用 overrides.css（集成补丁没被注入）")

    # 11) assets 与 pipeline/site 同步
    for name in ("style.css", "reader.js", "overrides.css"):
        a, b = FRONT / name, SITE / "assets" / name
        if a.exists() and b.exists() and a.read_bytes() != b.read_bytes():
            problems.append(f"book/site/assets/{name} 与 pipeline/site/{name} 不一致（构建产物陈旧）")

    # 12) 目录条目与已发布章一致
    published = sorted(pages)
    if toc.count("data-chapter=") != len(published):
        problems.append(f"toc.html 目录条目 {toc.count('data-chapter=')} 与已发布章 {len(published)} 不一致")
    for ch in published:
        if f'href="read/chapter-{ch:02d}.html"' not in toc:
            problems.append(f"toc.html 缺少第 {ch} 章链接")

    if problems:
        print(f"发现 {len(problems)} 处问题：")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print(f"OK：{len(pages)} 章 + 主页 + 目录，结构自检通过（含布局容器子项与结构计数保真）")


if __name__ == "__main__":
    main()
