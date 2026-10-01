#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""组装 GitHub Pages 多页阅读站点（主页 / 目录 / 逐章正文 / 中英对照）。

前端（HTML 模板 + style.css + reader.js）由视觉模型设计，源文件在 pipeline/site/；
本脚本只做「占位符替换」，把结构骨架 + 双语片段填进模板。

用法:
    python3 pipeline/build_site.py            # 全部章节
    python3 pipeline/build_site.py 1 2 3      # 指定章

产物:
    book/site/index.html
    book/site/toc.html
    book/site/read/chapter-NN.html
    book/site/assets/{style.css,reader.js,overrides.css,images/*.svg}

不变量：
  * 目录条目与「全书 N 章」一律取自**实际有译文的章节**，不是模板常量；
  * 陈旧的逐章页面与插图会被清理，撤下的章节不会继续发布（CI 直接部署 book/site）。
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_html import PLACEHOLDER_RE, expand, mini_to_html  # noqa: E402
from build_markdown import CHAP_DIR, FIG_MANIFEST, ZH_DIR, cn_num  # noqa: E402

SRC_DIR = Path(__file__).resolve().parent / "site"   #视觉模型设计的前端源文件
SEG_DIR = ROOT / "sources" / "work" / "segments"
IMG_DIR = ROOT / "book" / "images"
OUT = ROOT / "book" / "site"

REPO_URL = "https://github.com/0xVanfer/snowmoon-zh-cn"
SITE_URL = "https://snowmoon.vanfer.tech/"
UPSTREAM_URL = "https://vitalik.eth.limo/snowmoon/"
CONTACT_EMAIL = "vanfer@vanfer.tech"
SITE_TITLE = "雪月 Snowmoon · 中文版"
TOTAL_WORDS = "约 14.6 万"
CHAPTERS = list(range(1, 33))

PH_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def segs_of(p: Path, required: bool = True) -> dict[str, str]:
    if not p.exists():
        if required:
            raise SystemExit(f"缺少必需文件 {p.relative_to(ROOT)}")
        return {}
    return {s["id"]: s["text"] for s in load_json(p)["segments"]}


def build_date() -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        return out or "—"
    except Exception:  # noqa: BLE001
        return "—"


def block_ids(blk: dict) -> list[str]:
    return [m.group(1) for m in PLACEHOLDER_RE.finditer("".join(blk.get("segs", [])))]


def chapter_meta(ch: int) -> tuple[str | None, list[str]]:
    """从骨架里取「标题片段 id」与「卷首日期块的全部片段 id」。

    不再按 s0001/s0002/s0003 这类下标猜——那依赖「每章都有 h1、日期后紧跟正文」的假设。
    """
    data = load_json(CHAP_DIR / f"chapter-{ch:02d}.json")
    title_id: str | None = None
    dateline: list[str] = []
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind == "title" and title_id is None:
            ids = block_ids(blk)
            title_id = ids[0] if ids else None
        elif kind == "dateline-open" and not dateline:
            dateline = block_ids(blk)
    return title_id, dateline


def check_sync(ch: int, *seg_maps: dict[str, str]) -> None:
    """骨架引用的每个片段都必须在给定片段表里存在。

    只在 expand() 里兜底是不够的：章标题、卷首日期这类块在站点侧由模板渲染、
    根本不走 expand，id 失配会悄无声息。这里在构建前一次性全量核对。
    """
    data = load_json(CHAP_DIR / f"chapter-{ch:02d}.json")
    ids = set(PLACEHOLDER_RE.findall(json.dumps(data, ensure_ascii=False)))
    for i, segs in enumerate(seg_maps):
        missing = sorted(ids - set(segs))
        if missing:
            raise SystemExit(
                f"chapter-{ch:02d}: 骨架引用的片段在第 {i + 1} 份片段表里缺失 {missing[:4]}"
                f"（译文与骨架不同步）")


def render_blocks(ch: int, segs: dict[str, str], captions: dict[str, str],
                  prefix: str, zh: bool = False) -> str:
    """把一章的结构骨架 + 指定语言的片段渲染成正文 HTML。

    章标题与开篇日期由模板的 `.chapter-heading` 统一渲染（中英各一行，随语言模式收敛），
    正文流里不再重复一遍；章节中段的场景分隔（scene-break）照旧保留。

    [用户请求] `zh=True` 时 `<e>`/`<i>` 渲染成加粗而不是斜体（中文不用斜体）。
    """
    data = load_json(CHAP_DIR / f"chapter-{ch:02d}.json")
    out: list[str] = []
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind in ("title", "dateline-open"):
            continue
        if kind == "scene-break":
            vals = [segs[i] for i in block_ids(blk) if segs.get(i)]
            if not vals:
                continue
            out.append(f'<p class="scene-break">{mini_to_html(" · ".join(vals), zh)}</p>')
        elif kind == "rule":
            out.append('<hr class="rule">')
        elif kind == "figure":
            for f in blk.get("figures", []):
                cap = captions.get(f[:-4], "")
                alt = html.escape(cap or f"插图 {f[:-4]}", quote=True)
                out.append(f'<figure class="fig"><img src="{prefix}images/{f}" alt="{alt}"'
                           f' title="{alt}" loading="lazy" decoding="async"></figure>')
            if blk.get("skeleton"):
                out.append(expand(blk["skeleton"], segs, zh))
        elif kind == "p":
            inner = expand(blk.get("skeleton", ""), segs, zh)
            inner = re.sub(r"^<p>|</p>$", "", inner)
            # 片段里的颜色写成完整声明（color:#rrggbb），这里两处都要认，
            # 否则「整段对话加同色左侧色条」永远不生效（历史 bug）。
            m = re.fullmatch(r'<span style="(?:color:)?(#[0-9a-f]{6})">.*</span>[。！？…，]*',
                             inner, re.S)
            rail = f' class="dialog railed" style="color:{m.group(1)}"' if m else ' class="dialog"'
            out.append(f"<p{rail}>{inner}</p>")
        else:
            out.append(expand(blk.get("skeleton", ""), segs, zh))
    return "\n".join(x for x in out if x.strip())


def discover_chapters() -> list[int]:
    """全部可能有译文的章 = 骨架文件 ∪ 译文文件。

    [P1] 此前是写死的 `range(1, 33)`：第 33 章即使有了骨架和译文也会被静默丢弃，
    而六道闸门无一报警。章号应当由磁盘上真实存在的东西决定。
    """
    found = set(CHAPTERS)
    found.update(int(re.search(r"chapter-(\d+)\.json$", p.name).group(1))
                 for p in CHAP_DIR.glob("chapter-*.json") if re.search(r"chapter-(\d+)\.json$", p.name))
    found.update(int(re.search(r"chapter-(\d+)\.zh\.json$", p.name).group(1))
                 for p in ZH_DIR.glob("chapter-*.zh.json") if re.search(r"chapter-(\d+)\.zh\.json$", p.name))
    return sorted(found)


def prev_of(ch: int, chapters: list[int]) -> int | None:
    i = chapters.index(ch)
    return chapters[i - 1] if i > 0 else None


def next_of(ch: int, chapters: list[int]) -> int | None:
    i = chapters.index(ch)
    return chapters[i + 1] if i + 1 < len(chapters) else None


def toc_items(href_prefix: str, chapters: list[int], datelines: dict[int, str]) -> str:
    """目录条目：构建脚本产出，模板只负责放进 <ol> 里。

    结构与 pipeline/site/toc.html 里写明的约定一致：
    `li[data-chapter] > a.chapter-link`，内含 `.chapter-title-zh`、
    `.chapter-title-en`、`.chapter-dateline`、`.chapter-status`。
    """
    out = []
    for ch in chapters:
        out.append(
            f'<li data-chapter="{ch}">'
            f'<a class="chapter-link" href="{href_prefix}chapter-{ch:02d}.html">'
            f'<span class="chapter-title-zh">第{cn_num(ch)}章</span>'
            f'<span class="chapter-title-en" lang="en">Chapter {ch}</span>'
            f'<span class="chapter-dateline">{html.escape(datelines.get(ch, ""))}</span>'
            f'<span class="chapter-status"></span>'
            f'</a></li>')
    return "\n".join(out)


def inject_overrides(page: str, prefix: str) -> str:
    """把集成补充样式挂在 style.css 之后（视觉模型的产出保持原样，补丁单独一份文件）。"""
    if "</head>" not in page:
        raise SystemExit("页面模板缺少 </head>，无法注入 overrides.css")
    link = f'<link rel="stylesheet" href="{prefix}overrides.css">\n'
    return page.replace("</head>", link + "</head>", 1)


def fill(template: str, values: dict[str, str], where: str) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise SystemExit(f"{where}: 模板占位符 {{{{{key}}}}} 没有对应取值")
        return values[key]
    out = PH_RE.sub(sub, template)
    left = PH_RE.findall(out)
    if left:
        raise SystemExit(f"{where}: 仍有未替换占位符 {sorted(set(left))[:6]}")
    return out


def build() -> None:
    all_chapters = discover_chapters()
    requested = sorted({int(x) for x in sys.argv[1:]}) or all_chapters
    # [P1] 插图清单缺失曾经静默降级：captions 变成空 dict，112 处 alt + 56 处图注
    # 全部退化成「插图 chapter-04-fig-01」这类占位串，而六道闸门全绿。
    # 清单是这些文案的唯一来源，缺了就必须在这里停住。
    if not FIG_MANIFEST.exists():
        raise SystemExit(
            f"缺少插图清单 {FIG_MANIFEST.relative_to(ROOT)}："
            f"没有它就无法生成图注与 alt，只能退化成占位串。请先跑 make_figures.py apply。")
    captions = {k: v.get("caption", "") for k, v in load_json(FIG_MANIFEST).items()}

    # 实际会发布的章 = 有译文的章。目录、章数、上下章导航全部以它为准。
    chapters = [ch for ch in all_chapters if (ZH_DIR / f"chapter-{ch:02d}.zh.json").exists()]
    if not chapters:
        raise SystemExit("没有任何译文，未组装站点")

    titles_zh: dict[int, str] = {}
    datelines: dict[int, str] = {}
    datelines_en: dict[int, str] = {}
    for ch in chapters:
        zh = segs_of(ZH_DIR / f"chapter-{ch:02d}.zh.json")
        en = segs_of(SEG_DIR / f"chapter-{ch:02d}.src.json", required=False)
        title_id, dl_ids = chapter_meta(ch)
        titles_zh[ch] = zh.get(title_id or "", f"第{cn_num(ch)}章")
        parts = [zh[i] for i in dl_ids if zh.get(i)]
        datelines[ch] = " · ".join(parts)
        parts_en = [en[i] for i in dl_ids if en.get(i)]
        datelines_en[ch] = " · ".join(parts_en)

    common = dict(REPO_URL=REPO_URL, SITE_URL=SITE_URL, UPSTREAM_URL=UPSTREAM_URL,
                  CONTACT_EMAIL=CONTACT_EMAIL, SITE_TITLE=SITE_TITLE,
                  CHAPTER_COUNT=str(len(chapters)), TOTAL_WORDS=TOTAL_WORDS,
                  BUILD_DATE=build_date())
    toc_html = toc_items("read/", chapters, datelines)

    # ---- 计划阶段：先把每一章的正文渲染成字符串，**全部校验通过**才开始写盘 ----
    # [P1] 旧顺序是「剪图片 → 写 index/toc → 逐章 check_sync → 写章」：
    # 第 12 章校验失败时，前 11 章已经落盘、index/toc 已经是新的，
    # 而撤下的章节页还没被删 —— exit 1 的构建仍留下半新半旧的产物并继续被 CI 部署。
    pages: list[tuple[int, str]] = []
    for ch in requested:
        if ch not in chapters:
            print(f"skip ch{ch:02d}（无译文）")
            continue
        zh_segs = segs_of(ZH_DIR / f"chapter-{ch:02d}.zh.json")
        en_segs = segs_of(SEG_DIR / f"chapter-{ch:02d}.src.json", required=False)
        check_sync(ch, zh_segs, en_segs)
        values = dict(
            common, ASSET_PREFIX="../assets/",
            HOME_HREF="../index.html", TOC_HREF="../toc.html",
            PREV_HREF=f"chapter-{prev_of(ch, chapters):02d}.html" if prev_of(ch, chapters) else "../toc.html",
            NEXT_HREF=f"chapter-{next_of(ch, chapters):02d}.html" if next_of(ch, chapters) else "../toc.html",
            PREV_LABEL=f"上一章 · 第{cn_num(prev_of(ch, chapters))}章" if prev_of(ch, chapters) else "返回目录",
            NEXT_LABEL=f"下一章 · 第{cn_num(next_of(ch, chapters))}章" if next_of(ch, chapters) else "返回目录",
            # 底栏「上一章 / 下一章」：首章没有上一章、末章没有下一章，直接用 hidden 收起
            PREV_CH_HREF=f"chapter-{prev_of(ch, chapters):02d}.html" if prev_of(ch, chapters) else "",
            NEXT_CH_HREF=f"chapter-{next_of(ch, chapters):02d}.html" if next_of(ch, chapters) else "",
            PREV_CH_HIDDEN="" if prev_of(ch, chapters) else " hidden",
            NEXT_CH_HIDDEN="" if next_of(ch, chapters) else " hidden",
            TOC_ITEMS=toc_items("", chapters, datelines),
            CHAPTER_NO=str(ch),
            CHAPTER_TITLE_ZH=html.escape(titles_zh[ch], quote=True),
            CHAPTER_TITLE_EN=f"Chapter {ch}",
            CHAPTER_DATELINE_ZH=html.escape(datelines[ch], quote=True),
            CHAPTER_DATELINE_EN=html.escape(datelines_en[ch], quote=True),
            CONTENT_ZH=render_blocks(ch, zh_segs, captions, "../assets/", zh=True),
            CONTENT_EN=render_blocks(ch, en_segs, captions, "../assets/", zh=False),
        )
        tpl = (SRC_DIR / "chapter.html").read_text(encoding="utf-8")
        pages.append((ch, inject_overrides(fill(tpl, values, f"read/chapter-{ch:02d}.html"),
                                        "../assets/")))

    # ---- 落盘阶段：到这里所有校验都已经过了 ----
    OUT.mkdir(parents=True, exist_ok=True)
    first = chapters[0]
    # ---- 主页 / 目录页：同样在**计划阶段**渲染完 ----
    # [P1] 原来这两页在落盘阶段才 fill()，占位符缺失会发生在 assets 已拷贝、
    # .nojekyll 已写、陈旧章页还没剪之后 —— exit 1 的构建仍留下半新半旧的产物。
    home = (SRC_DIR / "index.html").read_text(encoding="utf-8")
    index_page = inject_overrides(fill(home, dict(
        common, ASSET_PREFIX="assets/", HOME_HREF="index.html", TOC_HREF="toc.html",
        PREV_HREF="toc.html", NEXT_HREF=f"read/chapter-{first:02d}.html",
        PREV_LABEL="上一章", NEXT_LABEL="开始阅读",
        TOC_ITEMS=toc_html,
        CHAPTER_NO=str(first), CHAPTER_TITLE_ZH=html.escape(titles_zh[first], quote=True),
        CHAPTER_TITLE_EN=f"Chapter {first}",
        CHAPTER_DATELINE_ZH=html.escape(datelines[first], quote=True), CHAPTER_DATELINE_EN="",
        CONTENT_ZH="", CONTENT_EN=""), "index.html"), "assets/")

    toc = (SRC_DIR / "toc.html").read_text(encoding="utf-8")
    toc_page = inject_overrides(fill(toc, dict(
        common, ASSET_PREFIX="assets/", HOME_HREF="index.html", TOC_HREF="toc.html",
        PREV_HREF="toc.html", NEXT_HREF=f"read/chapter-{first:02d}.html",
        PREV_LABEL="上一章", NEXT_LABEL="下一章",
        TOC_ITEMS=toc_html,
        CHAPTER_NO=str(first), CHAPTER_TITLE_ZH=html.escape(titles_zh[first], quote=True),
        CHAPTER_TITLE_EN=f"Chapter {first}",
        CHAPTER_DATELINE_ZH=html.escape(datelines[first], quote=True), CHAPTER_DATELINE_EN="",
        CONTENT_ZH="", CONTENT_EN=""), "toc.html"), "assets/")

    # ---- 落盘阶段：到这里所有校验都已经过了 ----
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "read").mkdir(parents=True, exist_ok=True)
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("style.css", "reader.js", "overrides.css"):
        shutil.copy2(SRC_DIR / name, assets / name)
    (assets / "images").mkdir(parents=True, exist_ok=True)
    published = set()
    for svg in sorted(IMG_DIR.glob("*.svg")):
        shutil.copy2(svg, assets / "images" / svg.name)
        published.add(svg.name)
    # 清理陈旧的已发布插图
    for old in (assets / "images").glob("*.svg"):
        if old.name not in published:
            old.unlink()
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    (OUT / "index.html").write_text(index_page, encoding="utf-8")
    (OUT / "toc.html").write_text(toc_page, encoding="utf-8")

    # ---- 目录页 ----
    for ch, page in pages:
        (OUT / "read" / f"chapter-{ch:02d}.html").write_text(page, encoding="utf-8")

    # 清理陈旧的逐章页面（撤下的章节不该继续被 CI 发布）
    keep = {f"chapter-{ch:02d}.html" for ch in chapters}
    for old in (OUT / "read").glob("chapter-*.html"):
        if old.name not in keep:
            old.unlink()

    print(f"站点已组装：{len(pages)} 章 + 主页 + 目录（全书 {len(chapters)} 章）→ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
