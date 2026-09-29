#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""组装单页 HTML 成品（中文排版在此落地）。

用法: python3 pipeline/build_html.py [章节号...]
产物: book/snowmoon-zh.html
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_markdown import CHAP_DIR, FIG_MANIFEST, ZH_DIR, cn_num, load_segs, oklch_to_hex  # noqa: E402

BOOK = ROOT / "book"
OUT = BOOK / "snowmoon-zh.html"
TAG_RE = re.compile(r"<(/?)([a-z]+)((?:\s[^>]*)?)(/?)>")
PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")


def mini_to_html(text: str) -> str:
    out: list[str] = []
    pos = 0
    links: list[str] = []
    for m in TAG_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()], quote=False))
        pos = m.end()
        closing, name, attrs, _ = m.groups()
        if name == "br":
            out.append("<br>")
        elif name == "c":
            sm = re.search(r'st="([^"]*)"', attrs)
            style = oklch_to_hex(sm.group(1)) if sm else ""
            if closing:
                out.append("</span>")
            else:
                out.append(f'<span style="{style}">' if style else "<span>")
        elif name == "f":
            out.append("</span>" if closing else '<span class="dz-script">')
        elif name == "b":
            out.append("</b>" if closing else "<b>")
        elif name in ("i", "e"):
            out.append("</em>" if closing else "<em>")
        elif name == "code":
            out.append("</code>" if closing else "<code>")
        elif name == "a":
            if closing:
                out.append(f'"{links.pop() if links else ""}">')
            else:
                hm = re.search(r'href="([^"]*)"', attrs)
                links.append(hm.group(1) if hm else "")
                out.append('<a href=')
        elif name in ("sup", "sub", "u", "small", "mark"):
            out.append(f"</{name}>" if closing else f"<{name}>")
    out.append(html.escape(text[pos:], quote=False))
    return "".join(out)


def expand(skeleton: str, segs: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: mini_to_html(segs.get(m.group(1), "")), skeleton)


CSS = """
:root{
  --ink:#1c1c1e; --ink-soft:#4a4a4f; --bg:#f6f4ef; --card:#fffdf8; --line:#ded8cc;
  --accent:#8a6d3b; --panel:#0a0e27; --panel-ink:#9cc2ff; --panel-line:#3d70c3;
  --measure:32em; --fs:17.5px;
}
@media (prefers-color-scheme: dark){
  :root{ --ink:#dcd8d0; --ink-soft:#a8a49c; --bg:#14141a; --card:#1b1b22; --line:#33333d;
         --accent:#c9a86a; --panel:#050510; --panel-ink:#88bbee; --panel-line:#1a3a6a; }
}
html[data-theme="dark"]{
  --ink:#dcd8d0; --ink-soft:#a8a49c; --bg:#14141a; --card:#1b1b22; --line:#33333d;
  --accent:#c9a86a; --panel:#050510; --panel-ink:#88bbee; --panel-line:#1a3a6a;
}
html[data-theme="light"]{
  --ink:#1c1c1e; --ink-soft:#4a4a4f; --bg:#f6f4ef; --card:#fffdf8; --line:#ded8cc;
  --accent:#8a6d3b; --panel:#0a0e27; --panel-ink:#9cc2ff; --panel-line:#3d70c3;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Songti SC","Noto Serif CJK SC","Source Han Serif SC","Georgia",serif;
  font-size:var(--fs); line-height:1.75;
  line-break:strict; word-break:normal; overflow-wrap:break-word;
  text-spacing-trim:trim-start;
}
.page{max-inline-size:var(--measure); margin:0 auto; padding:48px 22px 96px}
h1.title{font-size:1.9em; text-align:center; letter-spacing:.05em; margin:.2em 0 1.4em}
h2.chapter{font-size:1.5em; text-align:center; margin:3.5em 0 1.6em; letter-spacing:.12em}
h2.chapter::after{content:""; display:block; width:3em; height:2px; background:var(--accent);
  margin:.7em auto 0; opacity:.55}
p{margin:0; text-indent:2em; text-align:justify}
p.dialog{text-indent:2em}
p.dialog.railed{border-inline-start:3px solid currentColor; padding-inline-start:.55em; color:inherit}
.dateline{margin:1.1em 0 2.2em; text-align:center; text-indent:0; color:var(--ink-soft);
  font-size:.92em; letter-spacing:.06em}
.scene-break{text-align:center; text-indent:0; color:var(--ink-soft); font-size:.92em;
  margin:1.6em 0; letter-spacing:.08em}
hr{border:0; height:1px; background:var(--line); margin:2em auto; width:38%}
blockquote{margin:1.6em 0; padding:.2em 0 .2em 1em; border-inline-start:2px solid var(--line);
  color:var(--ink-soft); text-indent:0}
blockquote p{text-indent:0}
figure{margin:1.8em 0; text-align:center}
figure img{max-width:100%; height:auto; border-radius:10px; background:var(--panel); padding:6px}
.device-view{background:var(--panel); color:var(--panel-ink); border-radius:15px; padding:20px;
  margin:1.6em auto; text-align:center; font-family:"SF Mono","Courier New",monospace; font-size:.78em;
  overflow-x:auto; max-width:100%}
.device-view.wide-device-view{max-width:100%}
.device-view.device-view-left{text-align:left}
.device-view.device-view-left svg,.device-view.device-view-left img{margin-left:0!important; margin-right:auto!important}
.device-view h3{color:var(--panel-ink); border-bottom:2px solid var(--panel-line);
  padding-bottom:.5em; margin:.2em 0 1em; font-size:1.05em}
.device-view table{width:100%; border-collapse:collapse; margin:0 auto}
.device-view th,.device-view td{border:1px solid var(--panel-line); padding:10px;
  overflow-wrap:anywhere; text-align:start; color:var(--panel-ink)}
.device-view thead tr{background:rgba(255,255,255,.06)}
.device-view tbody tr:nth-child(odd){background:rgba(255,255,255,.03)}
.device-view button{background:rgba(255,255,255,.08); border:1px solid var(--panel-line);
  padding:.5em 1.2em; border-radius:3px; color:var(--panel-ink); font:inherit; cursor:default}
.device-view ul,.device-view ol{padding-inline-start:1.1em; margin:.2em 0; text-align:start}
.device-view input[type=range]{width:100%}
.device-view .dv-flex{display:flex; justify-content:space-between; width:100%}
.dz-card{background:var(--panel); color:#e6f4ff; border-radius:10px; padding:18px 22px; margin:1.4em auto;
  font-family:"TeX Gyre Chorus","Courier New",monospace; line-height:1.55; font-size:.95em;
  max-width:32em; text-align:center}
.dz-card .dz-line{margin:3px 0}
.dz-script{font-family:"TeX Gyre Chorus","Courier New",monospace; letter-spacing:.04em}
.toc{background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1.2em 1.4em;
  margin:2em 0 3em}
.toc h3{margin:.1em 0 .6em; font-size:1.05em; letter-spacing:.08em}
.toc ol{margin:0; padding-inline-start:1.6em; columns:2; column-gap:2em}
.toc a{color:inherit; text-decoration:none; border-bottom:1px dotted var(--line)}
.notice{background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1em 1.3em;
  color:var(--ink-soft); font-size:.9em; margin:2em 0}
.notice p{text-indent:0}
.controls{position:fixed; inset-block-start:14px; inset-inline-end:14px; z-index:20}
.controls button{background:var(--card); color:var(--ink); border:1px solid var(--line);
  border-radius:999px; padding:.45em .9em; font:inherit; font-size:.85em; cursor:pointer}
@media (max-width:640px){ :root{--fs:17px} .page{padding:26px 16px 64px} .toc ol{columns:1} }
@media print{ .controls{display:none} body{background:#fff; color:#000} .page{max-inline-size:none} }
"""

JS = """
(function(){
  var b=document.getElementById('theme-toggle');
  function label(){var d=document.documentElement.getAttribute('data-theme');
    b.textContent=(d==='dark'||(!d&&matchMedia('(prefers-color-scheme: dark)').matches))?'☀︎ 浅色':'☾ 深色';}
  b.addEventListener('click',function(){
    var cur=document.documentElement.getAttribute('data-theme');
    if(!cur){cur=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}
    document.documentElement.setAttribute('data-theme',cur==='dark'?'light':'dark');label();});
  label();
})();
"""


def render_chapter(ch: int, segs: dict[str, str], captions: dict[str, str]) -> str:
    data = json.loads((CHAP_DIR / f"chapter-{ch:02d}.json").read_text(encoding="utf-8"))
    out = [f'<section id="chapter-{ch}">', f'<h2 class="chapter">第{cn_num(ch)}章</h2>']
    for blk in data["blocks"]:
        kind = blk.get("kind")
        if kind == "title":
            continue
        if kind in ("dateline-open", "scene-break"):
            ids = [m.group(1) for m in PLACEHOLDER_RE.finditer("".join(blk.get("segs", [])))]
            vals = [segs.get(i, "") for i in ids if segs.get(i)]
            if not vals:
                continue
            cls = "dateline" if kind == "dateline-open" else "scene-break"
            out.append(f'<p class="{cls}">{mini_to_html(" · ".join(vals))}</p>')
        elif kind == "rule":
            out.append("<hr>")
        elif kind == "figure":
            for f in blk.get("figures", []):
                name = f[:-4]
                cap = captions.get(name, "")
                out.append(f'<figure><img src="images/{f}" alt="{html.escape(cap)}" '
                           f'title="{html.escape(cap)}" loading="lazy"></figure>')
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
    out.append("</section>")
    return "\n".join(x for x in out if x.strip())


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    captions: dict[str, str] = {}
    if FIG_MANIFEST.exists():
        captions = {k: v.get("caption", "") for k, v in
                    json.loads(FIG_MANIFEST.read_text(encoding="utf-8")).items()}
    chapters, toc = [], []
    for ch in todo:
        segs = load_segs(ch)
        if not segs:
            continue
        chapters.append(render_chapter(ch, segs, captions))
        toc.append(f'<li><a href="#chapter-{ch}">第{cn_num(ch)}章</a></li>')
    if not chapters:
        print("没有可组装的章节")
        return
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>雪月 Snowmoon · 中文版</title>
<style>{CSS}</style>
</head>
<body>
<div class="controls"><button id="theme-toggle" type="button">☾ 深色</button></div>
<div class="page">
<h1 class="title">雪月 · Snowmoon</h1>
<div class="notice">
<p>原作 <b>Snowmoon</b>，作者 Vitalik Buterin（<a href="https://vitalik.eth.limo/snowmoon/">vitalik.eth.limo/snowmoon</a>），
以 GPL-3.0-only 发布。本页为非官方中译本：正文译自英文原文，插图由英文版重绘为中文版，均未经原作者审定。
本项目同样以 GPL-3.0-only 发布。</p>
<p>原文用颜色区分说话人，本页保留颜色，并在纯对话段落左侧加了同色细条作为额外的视觉线索；
颜色仅作辅助，人物以上下文为准。</p>
</div>
<div class="toc"><h3>目录</h3><ol>{''.join(toc)}</ol></div>
{''.join(chapters)}
</div>
<script>{JS}</script>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    print(f"写入 {OUT.relative_to(ROOT)}：{len(chapters)} 章，{len(doc)/1024:.0f} KB")


if __name__ == "__main__":
    main()
