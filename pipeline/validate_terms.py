#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""术语卡片闸门：pipeline/terms.json 与 docs/explainer、译文、构建产物三向对账。

跑在 build_site.py **之后**——它校验的是最终产物（正文里有没有真的标出术语、
卡片里的章号链接能不能落到真实段落），而不是只校验数据文件自洽。

    python3 pipeline/validate_terms.py

退出码非 0 即发布中止。

[关于「跳过」]
被跳过的检查与通过的检查**分开计数并逐条打印**。把「没跑」写成和「跑过且通过」
一样的输出，等于删掉了「未执行即未通过」这条约定——CI 照样绿，内容其实没人验。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from terms import (CARD_FORBIDDEN, EXPLAINER_DIR, TERMS_JSON, TIER_LABEL,  # noqa: E402
                   WEIGHT_LABEL, load_concepts, page_url, ref_anchors)

ROOT = Path(__file__).resolve().parent.parent
SITE_READ = ROOT / "book" / "site" / "read"
ZH_DIR = ROOT / "translations" / "zh"

LIMITS = {"one_liner": 52, "analogy": 70}
NOTE_LIMIT = 24
REF_RE = re.compile(r"chapter-(\d+)\.md:(\d+)")
ID_RE = re.compile(r'id="(c\d\d-s\d+)"')
TERM_RE = re.compile(r'class="term" data-term="([^"]+)"')
CARD_ID_RE = re.compile(r'id="tc-([^"]+)"')

# ---- 气泡高度预算 ----
# 读者报过「卡内滚动不正常」：指针从词移向卡就会触发 mouseleave 把卡收掉，
# 于是卡下半截被截断且划不动。所以**不允许靠滚动兜底**，改成从结构上保证一屏装得下。
# 预算按最坏情况算：最窄常见视口 390px × 最大字号 24px。
#   卡片最宽 = 100vw − 2×edge(10) − padding(2×12) − border(2) ≈ 344px
#   字号     = 0.82em × 24px = 19.7px   → 每行 17 个汉字
#   行高     = 19.7 × 1.7 ≈ 33.5px
# 可用高度（844 − 顶栏 48 − 底栏 56 − 安全区 34）≈ 706px；预算留足余量取 560px。
# 实测 43 张卡的高度分布是 264–407px、中位 364px，全部远在预算内——
# 也就是说这个阈值平时不会拦人，它的作用是「将来有人往气泡里加内容时当场拦住」。
CARD_CONTENT_PX = 344
CARD_FONT_PX = 0.82 * 24
CARD_LINE_PX = CARD_FONT_PX * 1.7
CARD_CPL = int(CARD_CONTENT_PX // CARD_FONT_PX)          # 每行汉字数
CARD_BUDGET_PX = 560


def card_height_px(concept: dict, prereq_zh: list[str]) -> int:
    """保守估算一张卡渲染后的高度（行数 × 行高 + 段间距 + 内边距）。

    抬头那行是 flex + wrap，概念名与门槛标签会挤在同一行里，所以按**合并后的文本**算行数。
    （第一版把门槛标签的「字数」当成了「行数」，于是 10 个字的「专业，第一遍可跳过」
    被算成 10 行——四张最高的卡恰好全是 tier 3，全是这个 bug 造出来的。）
    """
    import math
    card = concept.get("card") or {}

    def lines(text: str) -> int:
        return max(1, math.ceil(len(text) / CARD_CPL))

    head = concept.get("zh", "") + " " + TIER_LABEL.get(concept.get("tier"), "")
    total = lines(head)
    total += lines(card.get("one_liner", ""))
    total += lines(card.get("analogy", ""))
    if prereq_zh:
        total += lines("先读：" + "、".join(prereq_zh))
    total += 1                                   # 「读完整教程 ↗」
    blocks = 4 + (1 if prereq_zh else 0)        # 段数（决定段间距）
    return int(total * CARD_LINE_PX + blocks * 0.5 * CARD_FONT_PX + 24)

problems: list[str] = []
notes: list[str] = []
skipped: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


concepts = load_concepts()

# ---- kill switch：内容工序没做完时功能整体关闭，而不是让构建失败 ----
if not concepts:
    print("术语卡片：pipeline/terms.json 缺失或 concepts 为空 —— 功能已关闭。")
    print("  跳过 14 项检查（不是通过）。构建产物里不应出现任何 .term 标注。")
    stray = sorted(p.name for p in SITE_READ.glob("chapter-*.html")
                   if TERM_RE.search(p.read_text(encoding="utf-8")))
    if stray:
        fail(f"terms.json 为空，但产物里仍有术语标注：{stray[:5]}")
        print(f"  ❌ {len(problems)} 项失败")
        raise SystemExit(1)
    print("  ✅ 产物中确认无 .term 标注，关闭状态自洽")
    raise SystemExit(0)

by_id = {c["id"]: c for c in concepts}
_heights: list[int] = []
if len(by_id) != len(concepts):
    fail("terms.json: 概念 id 有重复")

# ---- 1. 概念 ↔ 文档 双射 ----
docs = sorted(p for p in EXPLAINER_DIR.glob("*/*.md") if p.name != "README.md")
doc_ids = {c["doc"] for c in concepts}
missing_docs = [c["doc"] for c in concepts if not (EXPLAINER_DIR / c["doc"]).exists()]
if missing_docs:
    fail(f"terms.json 指向的文档不存在：{missing_docs[:4]}")
undocumented = [str(p.relative_to(EXPLAINER_DIR)) for p in docs
                if p.relative_to(EXPLAINER_DIR).as_posix() not in doc_ids]
if undocumented:
    fail(f"这些科普文档没有对应的术语卡片：{undocumented[:4]}")
if len(concepts) != len(docs):
    fail(f"概念数 {len(concepts)} 与文档数 {len(docs)} 不一致")

# ---- 2. 每篇的字段与正文标题一致 ----
for c in concepts:
    f = EXPLAINER_DIR / c["doc"]
    if not f.exists():
        continue
    head = f.read_text(encoding="utf-8").splitlines()[0]
    m = re.match(r"# (\d\d) (.+?)（(.+?)）", head)
    if not m:
        fail(f"{c['doc']}: 标题行无法解析")
        continue
    if int(m.group(1)) != c["no"]:
        fail(f"{c['doc']}: 编号 {m.group(1)} 与 terms.json 的 {c['no']} 不一致")
    if m.group(2) != c["zh"]:
        fail(f"{c['doc']}: 概念名 {m.group(2)!r} 与 terms.json 的 {c['zh']!r} 不一致")

# ---- 3. 字段取值与长度 ----
for c in concepts:
    cid = c["id"]
    if c.get("tier") not in TIER_LABEL:
        fail(f"{cid}: tier {c.get('tier')!r} 不在 1/2/3 内")
    if c.get("mark") not in ("first", "all", "none"):
        fail(f"{cid}: mark {c.get('mark')!r} 不在 first/all/none 内")
    for pid in c.get("prereq") or []:
        if pid not in by_id:
            fail(f"{cid}: prereq 指向不存在的 id {pid!r}")
        if pid == cid:
            fail(f"{cid}: prereq 自引用")
    card = c.get("card") or {}
    for field, lim in LIMITS.items():
        v = (card.get(field) or "").strip()
        if not v:
            fail(f"{cid}: card.{field} 为空")
        elif len(v) > lim:
            fail(f"{cid}: card.{field} {len(v)} 字，超过 {lim}")
        for bad in CARD_FORBIDDEN:
            if bad in v:
                fail(f"{cid}: card.{field} 含禁用字符 {bad!r}（会原样露在正文页上）")
    if "forward" in card:
        fail(f"{cid}: card.forward 不该存在——气泡只讲最基础概念，前后文关系归完整教程页")
    # 高度预算：超了就装不进一屏，而卡内滚动在触屏上并不可靠
    pre = [by_id[p]["zh"] for p in (c.get("prereq") or []) if p in by_id]
    h = card_height_px(c, pre)
    _heights.append(h)
    if h > CARD_BUDGET_PX:
        fail(f"{cid}: 估算高度 {h}px 超过预算 {CARD_BUDGET_PX}px"
             f"（最坏情况：390px 视口 + 24px 字号，每行 {CARD_CPL} 字）")

# prereq 成环会让「建议先读」指回自己
seen_state: dict[str, int] = {}


def visit(node: str, stack: list[str]) -> None:
    if seen_state.get(node) == 2:
        return
    if node in stack:
        fail(f"prereq 成环：{' → '.join(stack + [node])}")
        return
    seen_state[node] = 1
    for nxt in by_id.get(node, {}).get("prereq") or []:
        if nxt in by_id:
            visit(nxt, stack + [node])
    seen_state[node] = 2


for cid in by_id:
    visit(cid, [])

# ---- 4. 别名全局唯一（否则构建期判不出该标成哪个概念）----
alias_owner: dict[str, str] = {}
for c in concepts:
    for a in c.get("aliases_zh") or []:
        prev = alias_owner.get(a)
        if prev and prev != c["id"]:
            fail(f"别名 {a!r} 同时属于 {prev!r} 与 {c['id']!r}")
        alias_owner[a] = c["id"]
    if c.get("mark") != "none" and not c.get("aliases_zh"):
        fail(f"{c['id']}: mark={c.get('mark')!r} 但 aliases_zh 为空，不可能有标注点")

# ---- 5. chapters[].ch 必须等于该文档实际引用的章集合 ----
anchors = ref_anchors(concepts)
for c in concepts:
    f = EXPLAINER_DIR / c["doc"]
    if not f.exists():
        continue
    cited = sorted({int(a) for a, _b in REF_RE.findall(f.read_text(encoding="utf-8"))})
    declared = sorted(x["ch"] for x in c.get("chapters") or [])
    if cited != declared:
        fail(f"{c['id']}: chapters 声明 {declared}，文档实际引用 {cited}")
    for x in c.get("chapters") or []:
        if x.get("weight") not in WEIGHT_LABEL:
            fail(f"{c['id']} ch{x['ch']}: weight {x.get('weight')!r} 非法")
        note = (x.get("note") or "").strip()
        if not note:
            fail(f"{c['id']} ch{x['ch']}: note 为空")
        elif len(note) > NOTE_LIMIT:
            fail(f"{c['id']} ch{x['ch']}: note {len(note)} 字，超过 {NOTE_LIMIT}")
        for bad in CARD_FORBIDDEN:
            if bad in note:
                fail(f"{c['id']} ch{x['ch']}: note 含禁用字符 {bad!r}")

# ---- 6. 译文片段存在（锚点必须指向真实片段）----
for c in concepts:
    for item in anchors.get(c["id"], []):
        if not item["seg"]:
            fail(f"{c['id']} 第{item['ch']}章:{item['line']}：行号索引解析不到片段")
            continue
        zhf = ZH_DIR / f"chapter-{item['ch']:02d}.zh.json"
        if not zhf.exists():
            fail(f"{c['id']}: 第{item['ch']}章没有译文")
            continue
        segs = {s["id"] for s in json.loads(zhf.read_text(encoding="utf-8"))["segments"]}
        if item["seg"] not in segs:
            fail(f"{c['id']}: 片段 {item['seg']} 不在第{item['ch']}章译文里")

# ---- 7. 产物级校验 ----
pages = sorted(SITE_READ.glob("chapter-*.html"))
if not pages:
    skipped.append("产物级校验（book/site/read/ 下没有章页，可能还没跑 build_site.py）")
else:
    # 7a. 每页 id 唯一（中英两栏若都挂同名 id，同一份 HTML 里就是重复 id）
    for p in pages:
        ids = ID_RE.findall(p.read_text(encoding="utf-8"))
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            fail(f"{p.name}: id 重复 {sorted(dup)[:4]}")
    # 7b. 参与标注的概念必须真的在正文里出现过
    annotated: set[str] = set()
    for p in pages:
        text = p.read_text(encoding="utf-8")
        page_terms = set(TERM_RE.findall(text))
        annotated.update(page_terms)
        # 逐页对账：正文里的每个触发点都要有对应的卡片，章尾的每张卡片都要有触发点。
        # 少一边就是死代码——孤儿卡片读者永远打不开，孤儿触发点点开是空泡。
        page_cards = set(CARD_ID_RE.findall(text))
        for cid in sorted(page_terms - page_cards):
            fail(f"{p.name}: 触发点 {cid!r} 没有对应的卡片（点开是空泡）")
        for cid in sorted(page_cards - page_terms):
            fail(f"{p.name}: 卡片 {cid!r} 在本页没有任何触发点（读者打不开）")
    for c in concepts:
        if c.get("mark") == "none":
            if c["id"] in annotated:
                fail(f"{c['id']}: 标了 mark=none，却在产物里被标注了")
            continue
        if c["id"] not in annotated:
            fail(f"{c['id']}: mark={c.get('mark')!r} 但全书没有任何标注点（别名可能已失效）")
    unknown = annotated - set(by_id)
    if unknown:
        fail(f"产物里出现了 terms.json 之外的概念：{sorted(unknown)[:4]}")
    # 7c. 卡片池：结构与链接
    card_pages = 0
    for p in pages:
        text = p.read_text(encoding="utf-8")
        cards = CARD_ID_RE.findall(text)
        if not cards:
            continue
        card_pages += 1
        for cid in cards:
            if cid not in by_id:
                fail(f"{p.name}: 卡片 {cid!r} 不在 terms.json 里")
        # 气泡里不允许出现前后文关系：章号列表、权重、说明、后续用途一律不进正文卡。
        # 这不只是「少渲染点东西」——章号列表一张卡能堆到二十多行，
        # 手机屏装不下，而卡内滚动在触屏上不可靠（指针移向卡会先触发 mouseleave 收卡）。
        for cls in ("term-card__chapters", "term-card__forward", "term-card__note",
                    "term-card__w", "term-card__en", "term-card__ch"):
            if cls in text:
                fail(f"{p.name}: 气泡里出现了 {cls}（前后文关系不该渲染进正文卡）")
        # 必须**有**详细链接，且指向生产地址。
        # 只校验「存在的链接是不是生产地址」是不够的：把链接整个删掉、或者改掉类名，
        # findall 匹配不到任何东西，循环体一次都不进，闸门照样放行。
        for card_html in re.findall(r'<div class="term-card" id="tc-[^"]+".*?</div>', text, re.S):
            links = re.findall(r'class="term-card__more" href="([^"]+)"', card_html)
            if not links:
                fail(f"{p.name}: 卡片缺少「读完整教程」链接（读者卡在这里就没处可去了）")
            for url in links:
                if not url.startswith("https://github.com/0xVanfer/snowmoon-zh-cn/blob/main/docs/explainer/"):
                    fail(f"{p.name}: 教程链接不是生产地址：{url}")
                    continue
                # 链接指向的是**仓库里的一个真实文件**：改了目录名或挪了文件，
                # 链接形状照样合法，读者点进去却是 GitHub 的 404。
                # 所以要把 URL 里的仓库相对路径取出来，在本地核对它真的存在。
                rel_path = url.split("/blob/main/", 1)[1]
                if not (ROOT / rel_path).exists():
                    fail(f"{p.name}: 教程链接指向仓库里不存在的文件：{rel_path}")
        # 卡片池容器绝不能带 hidden/display:none（会把后代一起藏掉）
        m = re.search(r'<div class="term-store"[^>]*>', text)
        if m and ("hidden" in m.group(0) or "display:none" in m.group(0).replace(" ", "")):
            fail(f"{p.name}: .term-store 容器带了 hidden/display:none，卡片会永远看不见")
        # 「一句一行」的断句不得落进可点术语内部。
        # 浏览器探针跑不了时（headless Chrome 起不来）用同一判据做确定性校验：
        # 模拟 reader.js 的文本节点遍历，凡是位于 .term 内部的文本节点一律跳过，
        # 因此 .term 里不可能被插入 .sentence-gap——只要 .term 内不含句末标点。
        for term_html in re.findall(r'<span class="term"[^>]*>.*?</span>', text, re.S):
            if re.search(r"[。！？…!?]", term_html):
                fail(f"{p.name}: 术语 {term_html[:40]!r} 内含句末标点，"
                     f"「一句一行」会在词中间断句，把可点区域切成两半")
                break
    # 7f. reader.js 里必须有「深链时跳过进度恢复」与「断句跳过 .term」两处守卫。
    # 这两处是无头环境跑不到的行为，只能静态确认守卫存在——缺了就是静默回归。
    reader = (ROOT / "pipeline" / "site" / "reader.js")
    if reader.exists():
        js = reader.read_text(encoding="utf-8")
        if "if (deepLink) return;" not in js:
            fail("reader.js: restoreVisible() 没有跳过深链场景，"
                 "点章号 chip 会被进度记忆覆盖、落回上次读的位置")
        # 「有没有调用 applyDeepLink()」不能只 grep 这几个字。
        # 曾经就栽在这里：定义在一个 IIFE、调用点在另一个 IIFE，那行 `applyDeepLink();`
        # 一直在文件里、静态检查一路绿灯，而运行时是一个 ReferenceError——深链从来没生效过。
        # 现在按作用域查：定义之后到调用点之间不允许再出现 IIFE 收尾。
        # 收尾在本文件里一律写作 `}());`（`}` + `()` + `)` + `;`），别只写前三个字符。
        IIFE_END = r"\}\s*\(\s*\)\s*\)\s*;"
        m_def = re.search(r"function applyDeepLink\s*\(", js)
        if not m_def:
            fail("reader.js: 没有 applyDeepLink() 的定义，"
                 "#cNN-sNNNN 深链不会生效")
        else:
            rest = js[m_def.end():]
            m_call = re.search(r"[\w.]*\bapplyDeepLink\s*\(\s*\)\s*;", rest)
            if not m_call:
                fail("reader.js: applyDeepLink() 定义了却没有调用点，"
                     "#cNN-sNNNN 深链静默失效")
            elif re.search(IIFE_END, rest[:m_call.start()]):
                fail("reader.js: applyDeepLink() 的调用点跨到了另一个 IIFE，"
                     "运行时会抛 ReferenceError、深链静默失效"
                     "（探针的未捕获错误断言会抓到）")
        if "closest('.term')" not in js:
            fail("reader.js: addSentenceGaps() 没有跳过 .term 内部，"
                 "「一句一行」会把可点的术语切成两半")
    else:
        skipped.append("reader.js 静态守卫检查（源文件不存在）")
    notes.append(f"产物级校验覆盖 {card_pages} 个含卡片的章页")
    if _heights:
        _s = sorted(_heights)
        notes.append(f"气泡高度估算（最坏情况 390px 视口 + 24px 字号）："
                     f"最低 {_s[0]}px / 中位 {_s[len(_s) // 2]}px / 最高 {_s[-1]}px，"
                     f"预算 {CARD_BUDGET_PX}px")

# ---- 8. 已知缺口：书里没有对应词的概念 ----
blind = [c["id"] for c in concepts if c.get("mark") == "none"]
if blind:
    notes.append(
        f"书里没有对应词、因此不参与正文标注的概念（{len(blind)} 个）：{', '.join(blind)}。"
        f"它们只能从 GitHub 的概念总表进入——这是数据事实，不是缺陷，但读者在正文里点不到它们。")

# ---- 输出 ----
print(f"术语卡片闸门：{len(concepts)} 个概念 / {sum(len(c.get('chapters') or []) for c in concepts)} 条章记录")
for n in notes:
    print(f"  · {n}")
if skipped:
    print("  跳过（未执行，不等于通过）：")
    for s in skipped:
        print(f"    - {s}")
if problems:
    print(f"\n❌ {len(problems)} 项失败：")
    for p in problems[:60]:
        print(f"  ! {p}")
    if len(problems) > 60:
        print(f"  …另有 {len(problems) - 60} 项")
    sys.exit(1)
print(f"\n✅ 全部通过（跳过 {len(skipped)} 项，已单列）")
