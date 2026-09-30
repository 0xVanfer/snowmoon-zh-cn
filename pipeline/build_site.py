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
    book/site/assets/{style.css,reader.js,images/*.svg}
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
SITE_URL = "https://0xvanfer.github.io/snowmoon-zh-cn/"
UPSTREAM_URL = "https://vitalik.eth.limo/snowmoon/"
CONTACT_EMAIL = "vanfer@vanfer.tech"
SITE_TITLE = "雪月 Snowmoon · 中文版"
TOTAL_WORDS = "约 14.6 万"
CHAPTERS = list(range(1, 33))

PH_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def segs_of(p: Path) -> dict[str, str]:
    return {s["id"]: s["text"] for s in load_json(p)["segments"]}


def build_date() -> str:
    import subprocess
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        return out or "—"
    except Exception:  # noqa: BLE001
        return "—"


def render_blocks(ch: int, segs: dict[str, str], captions: dict[str, str],
                  prefix: str) -> str:
    """把一章的结构骨架 + 指定语言的片段渲染成正文 HTML。

    章标题与开篇日期由模板的 `.chapter-heading` 统一渲染（中英各一行，随语言模式收敛），
    正文流里不再重复一遍；章节中段的场景分隔（scene-break）照旧保留。
    """
    data = load_json(CHAP_DIR / f"chapter-{ch:02d}.json")
    out: list[str] = []
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind in ("title", "dateline-open"):
            continue
        if kind == "scene-break":
            ids = [m.group(1) for m in PLACEHOLDER_RE.finditer("".join(blk.get("segs", [])))]
            vals = [segs.get(i, "") for i in ids if segs.get(i)]
            if not vals:
                continue
            out.append(f'<p class="scene-break">{mini_to_html(" · ".join(vals))}</p>')
        elif kind == "rule":
            out.append('<hr class="rule">')
        elif kind == "figure":
            for f in blk.get("figures", []):
                cap = captions.get(f[:-4], "")
                alt = html.escape(cap or f"插图 {f[:-4]}")
                out.append(f'<figure class="fig"><img src="{prefix}images/{f}" alt="{alt}"'
                           f' title="{alt}" loading="lazy" decoding="async"></figure>')
            if blk.get("skeleton"):
                out.append(expand(blk["skeleton"], segs))
        elif kind == "p":
            inner = expand(blk.get("skeleton", ""), segs)
            inner = re.sub(r"^<p>|</p>$", "", inner)
            m = re.fullmatch(r'<span style="(#[0-9a-f]{6})">.*</span>[。！？…，]*', inner, re.S)
            rail = f' class="dialog railed" style="color:{m.group(1)}"' if m else ' class="dialog"'
            out.append(f"<p{rail}>{inner}</p>")
        else:
            out.append(expand(blk.get("skeleton", ""), segs))
    return "\n".join(x for x in out if x.strip())


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
    todos = [int(x) for x in sys.argv[1:]] or CHAPTERS
    captions = {k: v.get("caption", "") for k, v in
                load_json(FIG_MANIFEST).items()} if FIG_MANIFEST.exists() else {}
    # 每章的中英通用信息（目录用），从年级片段里取
    titles_zh: dict[int, str] = {}
    titles_en: dict[int, str] = {}
    datelines: dict[int, str] = {}
    for ch in CHAPTERS:
        zh = segs_of(ZH_DIR / f"chapter-{ch:02d}.zh.json")
        en = segs_of(SEG_DIR / f"chapter-{ch:02d}.src.json")
        first = sorted(k for k in zh if re.match(rf"c{ch:02d}-s\d+$", k))[:3]
        titles_zh[ch] = zh.get(first[0], f"第{cn_num(ch)}章") if first else f"第{cn_num(ch)}章"
        titles_en[ch] = en.get(first[0], f"Chapter {ch}") if first else f"Chapter {ch}"
        dl = [zh.get(i, "") for i in first[1:3]]
        datelines[ch] = " · ".join(x for x in dl if x)
    common = dict(REPO_URL=REPO_URL, SITE_URL=SITE_URL, UPSTREAM_URL=UPSTREAM_URL,
                  CONTACT_EMAIL=CONTACT_EMAIL, SITE_TITLE=SITE_TITLE,
                  CHAPTER_COUNT=str(len(CHAPTERS)), TOTAL_WORDS=TOTAL_WORDS,
                  BUILD_DATE=build_date())

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "read").mkdir(parents=True, exist_ok=True)
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("style.css", "reader.js", "overrides.css"):
        shutil.copy2(SRC_DIR / name, assets / name)
    (assets / "images").mkdir(parents=True, exist_ok=True)
    for svg in sorted(IMG_DIR.glob("*.svg")):
        shutil.copy2(svg, assets / "images" / svg.name)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    # ---- 主页 ----
    home = (SRC_DIR / "index.html").read_text(encoding="utf-8")
    (OUT / "index.html").write_text(inject_overrides(fill(home, dict(
        common, ASSET_PREFIX="assets/", HOME_HREF="index.html", TOC_HREF="toc.html",
        PREV_HREF="toc.html", NEXT_HREF="read/chapter-01.html",
        PREV_LABEL="上一章", NEXT_LABEL="开始阅读",
        TOC_ITEMS=toc_items("read/", CHAPTERS, datelines),
        CHAPTER_NO="1", CHAPTER_TITLE_ZH=titles_zh[1], CHAPTER_TITLE_EN=titles_en[1],
        CHAPTER_DATELINE_ZH=datelines[1], CHAPTER_DATELINE_EN="",
        CONTENT_ZH="", CONTENT_EN=""), "index.html"), "assets/"), encoding="utf-8")

    # ---- 目录页 ----
    toc = (SRC_DIR / "toc.html").read_text(encoding="utf-8")
    (OUT / "toc.html").write_text(inject_overrides(fill(toc, dict(
        common, ASSET_PREFIX="assets/", HOME_HREF="index.html", TOC_HREF="toc.html",
        PREV_HREF="toc.html", NEXT_HREF="read/chapter-01.html",
        PREV_LABEL="上一章", NEXT_LABEL="下一章",
        TOC_ITEMS=toc_items("read/", CHAPTERS, datelines),
        CHAPTER_NO="1", CHAPTER_TITLE_ZH=titles_zh[1], CHAPTER_TITLE_EN=titles_en[1],
        CHAPTER_DATELINE_ZH=datelines[1], CHAPTER_DATELINE_EN="",
        CONTENT_ZH="", CONTENT_EN=""), "toc.html"), "assets/"), encoding="utf-8")

    # ---- 逐章正文 ----
    tpl = (SRC_DIR / "chapter.html").read_text(encoding="utf-8")
    built = 0
    for ch in todos:
        zh_p = ZH_DIR / f"chapter-{ch:02d}.zh.json"
        if not zh_p.exists():
            print(f"skip ch{ch:02d}（无译文）")
            continue
        prefix = "../assets/"
        zh_segs = segs_of(zh_p)
        en_segs = segs_of(SEG_DIR / f"chapter-{ch:02d}.src.json")
        prev_ch = ch - 1 if ch > 1 else None
        next_ch = ch + 1 if ch < CHAPTERS[-1] else None
        values = dict(
            common, ASSET_PREFIX=prefix,
            HOME_HREF="../index.html", TOC_HREF="../toc.html",
            PREV_HREF=f"chapter-{prev_ch:02d}.html" if prev_ch else "../toc.html",
            NEXT_HREF=f"chapter-{next_ch:02d}.html" if next_ch else "../toc.html",
            PREV_LABEL=f"上一章 · 第{cn_num(prev_ch)}章" if prev_ch else "返回目录",
            NEXT_LABEL=f"下一章 · 第{cn_num(next_ch)}章" if next_ch else "返回目录",
            # 底栏「上一章 / 下一章」：首章没有上一章、末章没有下一章，直接用 hidden 收起
            PREV_CH_HREF=f"chapter-{prev_ch:02d}.html" if prev_ch else "",
            NEXT_CH_HREF=f"chapter-{next_ch:02d}.html" if next_ch else "",
            PREV_CH_HIDDEN="" if prev_ch else " hidden",
            NEXT_CH_HIDDEN="" if next_ch else " hidden",
            TOC_ITEMS=toc_items("", CHAPTERS, datelines),
            CHAPTER_NO=str(ch),
            CHAPTER_TITLE_ZH=f"第{cn_num(ch)}章",
            CHAPTER_TITLE_EN=f"Chapter {ch}",
            CHAPTER_DATELINE_ZH=datelines[ch],
            CHAPTER_DATELINE_EN=f"{en_segs.get(f'c{ch:02d}-s0002', '')} · "
                                f"{en_segs.get(f'c{ch:02d}-s0003', '')}",
            CONTENT_ZH=render_blocks(ch, zh_segs, captions, prefix),
            CONTENT_EN=render_blocks(ch, en_segs, captions, prefix),
        )
        page = inject_overrides(fill(tpl, values, f"read/chapter-{ch:02d}.html"), prefix)
        (OUT / "read" / f"chapter-{ch:02d}.html").write_text(page, encoding="utf-8")
        built += 1
    print(f"站点已组装：{built} 章 + 主页 + 目录 → {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
