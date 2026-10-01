#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""阅读站点自检（结构，不校验文字）。

检查项：
  1. 页面齐全、占位符清空、双语两栏与交互控件在位（必需 id 按 reader.js 的查询契约钉死）；
  2. **双语两栏保真**：中英文两栏分别与章节骨架比结构元素计数、布局容器个数与
     容器内直接子项个数（不再只查英文栏，整栏替换成一句话会被 4/6 拦下）；
  3. **布局容器保真**（需要上游原文时）：内联 flex/grid/justify-content 的容器的直接
     子项文字序列，逐条与原文比对（任意标签，且按配平标签取内容）；
  4. **中文栏非空**：中文正文长度不得相对原文塌陷（防止「片段被静默替换成空串」）；
  5. 站内链接与图片可解析、且必须落在站点根内，插图文件与构建输入一致、alt/图注完整；
  6. 无 JS 降级规则在位；
  7. 目录条目与「实际发布的章」一致；
  8. assets 与 pipeline/site 同步（防止提交陈旧构建产物）。

章数与插图数不再硬编码：一律从实际构建输入推导（translations/zh 的译文、
book/images 的插图、sources/work/chapters 的骨架、sources/work/figures/manifest.json
的图注）。站点里多出或少掉一个文件都会报错——章页是**列目录**得到的，不是按
「1..32」挨个找的，所以 chapter-33.html 不可能再被静默漏检。

上游英文原文（sources/en/html）不入库，缺失时第 3 项与「对原文的结构计数」自动跳过
并提示；第 2/4/5 项不依赖它，照常执行。
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
FRONT = ROOT / "pipeline" / "site"
# 以下四个与构建脚本同口径（build_markdown.CHAP_DIR/ZH_DIR/FIG_MANIFEST、build_site.IMG_DIR）
ZH_DIR = ROOT / "translations" / "zh"
CHAP_DIR = ROOT / "sources" / "work" / "chapters"
FIG_MANIFEST = ROOT / "sources" / "work" / "figures" / "manifest.json"
IMG_DIR = ROOT / "book" / "images"
REPO_URL = "https://github.com/0xVanfer/snowmoon-zh-cn"
SITE_URL = "https://snowmoon.vanfer.tech/"
EMAIL = "vanfer@vanfer.tech"

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "param", "source", "track", "wbr", "path", "rect", "line", "circle", "polygon",
             "polyline", "ellipse", "use", "stop"}
TAGSCAN = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>")
TAG_RE = re.compile(r"<[^>]+>")
FLEX_STYLE_RE = re.compile(r"display\s*:\s*(?:flex|grid)|justify-content", re.I)
# 结构标记：这些标签数量由抽取层保留，翻译不可能增删，因此可以逐栏比对
STRUCT_TAGS = ("table", "tr", "td", "th", "blockquote", "li")
DEVICE_RE = re.compile(r'class="[^"]*device-view', re.I)
FLEX_TAG_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9]*\b[^>]*style=\"[^\"]*\"[^>]*>")
FIGURE_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.S | re.I)
CHAPTER_FILE_RE = re.compile(r"chapter-(\d+)\.html$")
ZH_FILE_RE = re.compile(r"chapter-(\d+)\.zh\.json$")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

# 结构契约：reader.js 真正查询、CSS 真正选择、跳转链接真正指向的 id。
# 改名 = 双语两栏 / 翻页 / 面板 / 章末跳转整条链路静默失效，而页面不报错：
#   reader.js:357 `if (!main) return;` —— #reader-main 一改名，第 2 段整个布局与翻页就没了；
#   reader.js:1197 章边界跳转靠 #nav-prev/#nav-next；reader.js:45 的 skip-link 指向 #reader-main；
#   style.css/overrides.css 的无 JS 降级按 html:not([data-js]) #pane-zh / #lang-tabs 选。
CHAPTER_IDS = (
    "reader-main", "pane-zh", "pane-en",          # 双语两栏与排版
    "topbar", "bottombar", "progress-bar", "page-indicator",  # 顶栏/底栏/进度
    "lang-tabs",                                   # 对照标签页
    "nav-prev", "nav-next", "nav-toc",             # 章首/章末跳转
    "drawer", "drawer-toc", "settings-panel", "scrim",  # 目录抽屉与设置面板
    "btn-drawer", "btn-lang", "btn-settings", "btn-prev-screen", "btn-next-screen",
)
# 主页/目录页上 reader.js 也按 id 取的元素
PAGE_IDS = {"index.html": ("continue-reading",), "toc.html": ("toc-list", "toc-progress")}


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


def flex_containers(text: str):
    """text 里所有带内联 flex/grid/justify-content 的布局容器（含自身标签）。"""
    for m in FLEX_TAG_RE.finditer(text):
        if FLEX_STYLE_RE.search(m.group(0)):
            el = balanced_element(text, m.start())
            if el:
                yield el


def _inner(el: str) -> str:
    return el[el.index(">") + 1: el.rindex("</")] if "</" in el else ""


def flex_rows(text: str) -> Counter:
    """某一片段里所有布局容器的「直接子元素文字序列」。"""
    rows: Counter = Counter()
    for el in flex_containers(text):
        kids = [k for k in (norm(c) for c in direct_children(_inner(el))) if k]
        if kids:
            rows[tuple(kids)] += 1
    return rows


def flex_arity(text: str) -> Counter:
    """布局容器的「直接子元素个数」分布（与文字无关，故中英文两栏可同口径比）。

    只比个数、不比标签名：中文栏把 <e>/<i> 渲染成粗体（build_site.render_blocks），
    标签名本就可能与英文栏不同。要防的是「整个容器被拍平成一条文本节点」——
    那种情况下 arity 从 N 掉到 1，刻度分布与按项分页一起失效。
    """
    out: Counter = Counter()
    for el in flex_containers(text):
        n = len(direct_children(_inner(el)))
        if n:
            out[n] += 1
    return out


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
    p = CHAP_DIR / f"chapter-{ch:02d}.json"
    if not p.exists():
        return 0, 0, 0
    blocks = json.loads(p.read_text(encoding="utf-8"))["blocks"]
    figs = [b for b in blocks if b.get("kind") == "figure"]
    leftover = sum(1 for b in figs if b.get("skeleton"))
    return len(figs), sum(len(b.get("figures", [])) for b in figs), leftover


def rendered_skeleton(ch: int) -> str | None:
    """本章构建时真正会进正文流的那部分骨架 HTML。

    title / dateline-open 走 .chapter-heading 模板渲染，不在正文里，比对时要排除；
    读不到骨架返回 None（宁可不比，也不能拿空串当「结构本来就是空的」）。
    """
    p = CHAP_DIR / f"chapter-{ch:02d}.json"
    if not p.exists():
        return None
    blocks = json.loads(p.read_text(encoding="utf-8"))["blocks"]
    return "\n".join(b.get("skeleton", "") for b in blocks
                     if b.get("kind") not in ("title", "dateline-open"))


def expected_chapters() -> list[int] | None:
    """应当发布的章 = 有译文的章（与 build_site.build() 同口径）；没有译文目录返回 None。"""
    if not ZH_DIR.is_dir():
        return None
    return sorted(int(m.group(1)) for m in
                  (ZH_FILE_RE.match(p.name) for p in ZH_DIR.glob("chapter-*.zh.json")) if m)


def figure_manifest() -> dict[str, str]:
    """图注的事实源：文件名 → 图注（sources/work/figures/manifest.json）。"""
    if not FIG_MANIFEST.exists():
        return {}
    data = json.loads(FIG_MANIFEST.read_text(encoding="utf-8"))
    return {f"{k}.svg": v.get("caption", "") or "" for k, v in data.items()}


def is_placeholder_caption(text: str) -> bool:
    """「插图」「插图 chapter-04-fig-01」是 build_site/build_markdown 缺图注时的兜底串。

    那种串说明「图注没了」，不能当成有效图注；真正的中文图注一定含汉字。
    """
    s = (text or "").strip()
    if not s:
        return True
    m = re.fullmatch(r"插图[\s:：]+(\S+)", s)
    return bool(m) and not CJK_RE.search(m.group(1))


def figures_of(text: str) -> list[tuple[str, str, str]]:
    """逐个 <figure> 返回 (图片文件名, alt, <figcaption> 文本)。"""
    out: list[tuple[str, str, str]] = []
    for m in FIGURE_RE.finditer(text):
        el = m.group(0)
        img = re.search(r"<img\b[^>]*>", el, re.I)
        src = alt = ""
        if img:
            a = re.search(r"\balt\s*=\s*\"([^\"]*)\"", img.group(0), re.I)
            s = re.search(r"\bsrc\s*=\s*\"([^\"]*)\"", img.group(0), re.I)
            alt = htmlmod.unescape(a.group(1)) if a else ""
            src = s.group(1).rsplit("/", 1)[-1] if s else ""
        cap = ""
        c = re.search(r"<figcaption\b[^>]*>(.*?)</figcaption>", el, re.S | re.I)
        if c:
            cap = norm(c.group(1))
        out.append((src, alt, cap))
    return out


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


def site_target(url: str, base: Path) -> Path:
    """站内 URL → 磁盘路径：以 / 开头按站点根解释，其余按所在目录（纯文件系统语义）。"""
    return (SITE / url.lstrip("/")) if url.startswith("/") else (base / url)


def anchor_problems(name: str, text: str) -> list[str]:
    """页内锚点（skip-link、跳转链接）必须指向本页真实存在的 id。"""
    ids = set(re.findall(r'\bid="([^"]+)"', text))
    return [f"{name}: 锚点 {frag} 指向本页不存在的 id"
            for frag in sorted(set(re.findall(r'href="#([^"]+)"', text)) - ids)]


def main() -> None:
    problems: list[str] = []
    if not (SITE / "index.html").exists():
        print("站点未构建：book/site/index.html 不存在")
        sys.exit(1)

    # 1) 文件齐全：章页从实际产物里**列出来**，而不是按硬编码章数挨个找
    need = ["index.html", "toc.html", "assets/style.css", "assets/reader.js", ".nojekyll"]
    for f in need:
        if not (SITE / f).exists():
            problems.append(f"缺少 {f}")
    pages: dict[int, str] = {}
    read_dir = SITE / "read"
    found: dict[int, Path] = {}
    for p in sorted(read_dir.glob("chapter-*.html")) if read_dir.is_dir() else []:
        m = CHAPTER_FILE_RE.match(p.name)
        if not m:
            problems.append(f"read/{p.name} 不符合 chapter-NN.html 命名，不会被检查却仍会被 CI 发布")
            continue
        found[int(m.group(1))] = p
    for ch, p in sorted(found.items()):
        pages[ch] = p.read_text(encoding="utf-8")
    expected = expected_chapters()
    if expected is None:
        problems.append(f"缺少 {ZH_DIR.relative_to(ROOT)}，无法确定应当发布哪几章")
    else:
        for ch in expected:
            if ch not in found:
                problems.append(f"缺少 read/chapter-{ch:02d}.html")
        extra = sorted(set(found) - set(expected))
        if extra:
            problems.append(f"read/ 下有 {len(extra)} 个没有译文的章页仍会被发布："
                            f"{[f'chapter-{c:02d}.html' for c in extra][:5]}")
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

    # 4) 每章双语两栏 + 交互控件（id 清单是 reader.js 的查询契约，不是可选清单）
    for ch, text in pages.items():
        for attr in ('data-lang="zh"', 'data-lang="en"'):
            if attr not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 {attr} 正文栏")
        for cid in CHAPTER_IDS:
            if f'id="{cid}"' not in text:
                problems.append(f"chapter-{ch:02d}: 缺少 id=\"{cid}\"（reader.js 会按它取元素）")
        problems.extend(anchor_problems(f"read/chapter-{ch:02d}.html", text))
    for name, text in (("index.html", index), ("toc.html", toc)):
        for cid in PAGE_IDS[name]:
            if f'id="{cid}"' not in text:
                problems.append(f"{name}: 缺少 id=\"{cid}\"（reader.js 会按它取元素）")
        problems.extend(anchor_problems(name, text))

    # 5) 双语两栏保真：中英文**分别**与章节骨架比（只看英文栏时，整栏换成一句话照样通过）
    for ch, text in pages.items():
        skel = rendered_skeleton(ch)
        if skel is None:
            problems.append(f"chapter-{ch:02d}: 缺少 {CHAP_DIR.relative_to(ROOT)}/chapter-{ch:02d}.json，"
                            f"无法比对双语两栏的结构保真")
            continue
        want_s = struct_counts(skel)
        want_a = flex_arity(skel)
        for lang in ("zh", "en"):
            pane = pane_text(text, lang)
            if not pane:
                problems.append(f"chapter-{ch:02d}: {lang} 栏为空")
                continue
            # 5.1 结构元素计数：两栏都不得少于骨架
            got_s = struct_counts(pane)
            for tag, n in want_s.items():
                if n and got_s.get(tag, 0) < n:
                    problems.append(f"chapter-{ch:02d}: {lang} 栏 <{tag}> 数量减少"
                                    f"（骨架 {n}，{lang} 栏 {got_s.get(tag, 0)}）")
            # 5.2 布局容器：个数与「容器内直接子项个数」都不得少；
            #     一栏里一个都没有也算失败（不能指望另一栏顶数）
            got_a = flex_arity(pane)
            for arity, n in want_a.items():
                if got_a.get(arity, 0) < n:
                    problems.append(f"chapter-{ch:02d}: {lang} 栏布局容器（{arity} 个直接子项）只剩 "
                                    f"{got_a.get(arity, 0)} 处，骨架有 {n} 处")
            if sum(want_a.values()) and not sum(got_a.values()):
                problems.append(f"chapter-{ch:02d}: {lang} 栏里一个布局容器都没有（骨架有 "
                                f"{sum(want_a.values())} 个）")
            # 5.3 插图块数：两栏都得等于骨架里那张数
            _, fig_total, _ = chapter_figures(ch)
            out_fig = len(FIGURE_RE.findall(pane))
            if out_fig != fig_total:
                problems.append(f"chapter-{ch:02d}: {lang} 栏插图数量不符"
                                f"（骨架 {fig_total} 个 figure 块，{lang} 栏 {out_fig} 个）")
            # 5.4 终端面板（.device-view）：带 SVG 的会被搬进 <figure>，其余仍是
            #     .device-view。这些面板是 class 命名、没有内联 flex 样式，
            #     flex_arity / struct_counts 都看不见它们 —— 删光一整栏的终端面板
            #     而两栏计数不变时，没有任何检查会响。
            #     这条不依赖上游原文，因此放在这里而不是 7.3 那个 else 分支里。
            skel_dv = len(DEVICE_RE.findall(skel))
            out_dv = len(DEVICE_RE.findall(pane))
            if out_dv + fig_total < skel_dv:
                problems.append(f"chapter-{ch:02d}: {lang} 栏终端面板不足"
                                f"（骨架 {skel_dv} 个 .device-view，{lang} 栏 {out_dv} 个"
                                f" + {fig_total} 个 figure 块）")

    # 6) 中文栏不得塌陷（不依赖上游原文：没有原文时也必须查）
    for ch, text in pages.items():
        zh_len = len(norm(pane_text(text, "zh")))
        en_len = len(norm(pane_text(text, "en")))
        if en_len and zh_len < en_len * 0.25:
            problems.append(
                f"chapter-{ch:02d}: 中文栏疑似缺失（中文 {zh_len} 字符 / 英文 {en_len} 字符）")
        if zh_len < 2000:
            problems.append(f"chapter-{ch:02d}: 中文栏过短（{zh_len} 字符），正文可能没注入")

    # 7) 需要上游原文的检查
    if not SRC.exists():
        print("提示：sources/en/html 不存在（上游原文不入库），"
              "跳过「布局容器子项文字序列」与「结构计数对原文」两项；"
              "上面基于章节骨架的逐栏保真、中文栏长度、插图与链接检查照常执行")
    else:
        for ch, text in pages.items():
            src_file = SRC / f"chapter-{ch}.html"
            if not src_file.exists():
                problems.append(f"chapter-{ch:02d}: 缺少上游原文 {src_file.name}，无法比对结构")
                continue
            src_text = strip_noise(src_file.read_text(encoding="utf-8"))
            # 7.1 布局容器子项序列：只认英文栏。原文是英文，中文栏里的同名容器
            #     不能替英文栏顶数（否则删光英文栏的全部布局容器仍然 exit 0）。
            want = flex_rows(src_text)
            got = flex_rows(pane_text(text, "en"))
            for row, n in want.items():
                if got.get(row, 0) < n:
                    problems.append(
                        f"chapter-{ch:02d}: 布局容器子项丢失/错位 {list(row)}"
                        f"（原文 {n} 处，成品英文栏 {got.get(row, 0)} 处）")
            # 7.2 结构元素计数不得减少（英文栏对原文）
            sc, bc = struct_counts(src_text), struct_counts(pane_text(text, "en"))
            for tag, n in sc.items():
                if n and bc.get(tag, 0) < n:
                    problems.append(
                        f"chapter-{ch:02d}: <{tag}> 数量减少（原文 {n}，成品英文栏 {bc.get(tag, 0)}）")
            # 7.3 终端面板：带 SVG 的会变成 <figure>，其余仍保留 .device-view（两栏各算一次）
            fig_blocks, _fig_total, fig_leftover = chapter_figures(ch)
            src_dv = len(DEVICE_RE.findall(src_text))
            for lang in ("zh", "en"):
                pane = pane_text(text, lang)
                out_dv = len(DEVICE_RE.findall(pane))
                if src_dv != out_dv + fig_blocks - fig_leftover:
                    problems.append(
                        f"chapter-{ch:02d}: {lang} 栏终端面板数量不符（原文 {src_dv} 个，"
                        f"{lang} 栏 {out_dv} 个 .device-view + {fig_blocks} 个 figure 块"
                        f" − {fig_leftover} 个残留层）")

    # 8) 站内链接与图片可解析，且必须落在站点根之内
    site_root = SITE.resolve()
    for name, text, base in [("index.html", index, SITE), ("toc.html", toc, SITE)] + \
                            [(f"read/chapter-{c:02d}.html", t, SITE / "read") for c, t in pages.items()]:
        for attr, url in re.findall(r'(href|src)="([^"#?]+)"', text):
            if re.match(r"^(https?:|mailto:|data:|//)", url):
                continue
            # 只验「磁盘上存在吗」的话，href="/etc/hosts" 会解析到 /private/etc/hosts、
            # "../../../README.md" 会逃出站点根，两种都能通过。
            target = site_target(url, base)
            try:
                target.resolve().relative_to(site_root)
            except ValueError:
                problems.append(f"{name}: {attr}=\"{url}\" 逃出站点根（解析到 {target.resolve()}）")
                continue
            if not target.exists():
                where = "（以 / 开头，按站点根解析）" if url.startswith("/") else ""
                problems.append(f"{name}: {attr}=\"{url}\" 指向的文件不存在{where}")

    # 9) 插图文件与图注
    imgs = {p.name for p in (SITE / "assets" / "images").glob("*.svg")}
    if IMG_DIR.is_dir():
        # 站点里的插图必须正好是构建输入的那一批：多出来的是陈旧产物（CI 照发），
        # 少掉的等于静默少发一张——两件事都不该靠一个硬编码总数糊过去。
        published = {p.name for p in IMG_DIR.glob("*.svg")}
        only_site = sorted(imgs - published)
        lost = sorted(published - imgs)
        if only_site:
            problems.append(f"assets/images 有构建输入里没有的插图（仍会被发布）：{only_site[:4]}")
        if lost:
            problems.append(f"assets/images 少了 {len(lost)} 张构建输入里的插图：{lost[:4]}")
    refs: Counter = Counter()
    for text in pages.values():
        refs.update(re.findall(r"images/([A-Za-z0-9._-]+\.svg)", text))
    missing = sorted(set(refs) - imgs)
    if missing:
        problems.append(f"引用了不存在的插图：{missing[:4]}")
    unused = sorted(imgs - set(refs))
    if unused:
        problems.append(f"有插图未被任何页面引用：{unused[:4]}")
    # 9.1 alt 与图注：全站删光 alt、全站删光图注、alt 退化成「插图」三种都要被抓到。
    #     build_site.render_blocks 目前把图注写进 alt/title、不输出 <figcaption>，
    #     所以「有图注」按 <figcaption> 或 alt/title 任一存在且非占位串来判。
    manifest = figure_manifest()
    for ch, text in sorted(pages.items()):
        for lang in ("zh", "en"):
            for src, alt, cap in figures_of(pane_text(text, lang)):
                where = f"chapter-{ch:02d}: {lang} 栏 {src or '(无 src)'}"
                if not alt.strip():
                    problems.append(f"{where}: 插图没有 alt 文本")
                elif is_placeholder_caption(alt):
                    problems.append(f"{where}: alt 退化成占位串「{alt}」（真图注缺失）")
                if is_placeholder_caption(cap or alt):
                    problems.append(f"{where}: 没有图注（figcaption 与 alt/title 均为空或占位串）")
                if manifest and src in manifest:
                    want_cap = manifest[src]
                    if want_cap.strip() and alt != want_cap:
                        problems.append(f"{where}: alt 与图注事实源不符（manifest：{want_cap!r}）")

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
    print(f"OK：{len(pages)} 章 + 主页 + 目录，结构自检通过"
          f"（双语两栏逐栏对骨架的结构计数与布局容器保真、必需 id、插图 alt/图注、"
          f"站内链接落在站点根内、章数与插图数取自实际构建输入）")


if __name__ == "__main__":
    main()
