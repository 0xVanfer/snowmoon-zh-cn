#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""术语卡片的数据层：装载、正文标注、引用锚点解析。

供 build_site.py（生成正文标注与卡片池）与 validate_terms.py（闸门）共用——
两处各写一份匹配逻辑正是「同一规则两套实现」那类漂移的起点。

术语的中文别名**不能从文档标题推导**：H1 是描述性标签，实测「对抗补丁」「熵与信息论」
「异或与 Nim 和」在全书命中 0，而书里实际写的是「对抗攻击」「熵」「异或」。
`pipeline/terms.json` 里的 aliases_zh 全部由 `pipeline/scan` 实测得出。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLAINER_DIR = ROOT / "docs" / "explainer"
TERMS_JSON = ROOT / "pipeline" / "terms.json"
LINE_INDEX = ROOT / "pipeline" / "line_index.json"

# 「读完整教程」的落地页。指向生产仓库的 main 分支——教程正文是 Markdown + LaTeX，
# 交给 GitHub 渲染（表格、公式、标题大纲、相对链接全都现成），站点自己不实现渲染器。
REPO_BLOB = "https://github.com/0xVanfer/snowmoon-zh-cn/blob/main/docs/explainer"

TIER_LABEL = {1: "不需要背景", 2: "需要一点基础", 3: "专业，第一遍可跳过"}
WEIGHT_LABEL = {"load": "承重", "mid": "重要", "air": "背景"}

# 卡片正文会内联进章节页，这里禁止出现的字符：格式标记会原样露给读者
CARD_FORBIDDEN = ("$", "|", "**", "#", "`", "\n", "\r", "\t")


def load_concepts() -> list[dict]:
    """读 pipeline/terms.json。文件缺失或为空数组 = 功能关闭（kill switch）。

    刻意不抛错：内容工序没做完时站点应当照常可读，只是没有术语卡片，
    而不是整个构建失败。
    """
    if not TERMS_JSON.exists():
        return []
    data = json.loads(TERMS_JSON.read_text(encoding="utf-8"))
    return list(data.get("concepts") or [])


def page_url(doc: str) -> str:
    return f"{REPO_BLOB}/{doc}"


def alias_matcher(concepts: list[dict]) -> tuple[re.Pattern | None, dict[str, str]]:
    """建一张**全局**别名表 → (最长优先的正则, 别名 → 概念 id)。

    必须全局唯一且全局最长优先，不能每个概念各编各的：
      * 「零知识」属概念 4，而「零知识抵押」属概念 5——分表匹配会让 4 抢走 5 的词；
      * 「签名」属概念 6，而「基于哈希的签名」属概念 8——反向同理。
    """
    owner: dict[str, str] = {}
    for c in concepts:
        for a in c.get("aliases_zh") or []:
            prev = owner.get(a)
            if prev is not None and prev != c["id"]:
                raise SystemExit(
                    f"terms.json: 别名 {a!r} 同时属于 {prev!r} 与 {c['id']!r}；"
                    f"别名必须全局唯一，否则构建期无法判定该标注成哪个概念")
            owner[a] = c["id"]
    if not owner:
        return None, {}
    rx = re.compile("|".join(re.escape(a) for a in sorted(owner, key=len, reverse=True)))
    return rx, owner


def _wrap_matches(text: str, marked: set[str], rx: re.Pattern, owner: dict[str, str]) -> str:
    out: list[str] = []
    pos = 0
    for m in rx.finditer(text):
        cid = owner[m.group(0)]
        if cid in marked:          # mark="first"：本章已标过，后面不再重复打扰
            continue
        out.append(text[pos:m.start()])
        out.append(
            f'<span class="term" data-term="{cid}" tabindex="0" role="button"'
            f' aria-expanded="false">{m.group(0)}</span>')
        marked.add(cid)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def mark_terms(fragment: str, rx: re.Pattern | None, owner: dict[str, str],
               marked: set[str]) -> str:
    """在一块已渲染成 HTML 的正文里标注术语。

    只切文本节点，**绝不碰标签与属性**：正文里有说话人上色的 `<span style>`、
    译注气泡的 `<span class="tnote">`、以及图注 alt 里的引号，任何一处被改都会
    破坏既有的渲染与校验。

    译注气泡内部整体跳过：那里已经有一个可点区域，再套一层可点区域会得到
    嵌套交互元素，键盘和读屏都拿不准焦点落在哪。
    """
    if rx is None or not fragment:
        return fragment
    parts = re.split(r"(<[^>]*>)", fragment)
    in_tnote = False
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2:                                   # 标签
            if part.startswith('<span class="tnote"'):
                in_tnote = True
            elif part == "</span>" and in_tnote:
                in_tnote = False
            out.append(part)
            continue
        out.append(part if in_tnote or not part
                   else _wrap_matches(part, marked, rx, owner))
    return "".join(out)


class TermMarker:
    """按章标注术语。`mark="first"` 的「本章只标第一处」靠 marked 集合实现。

    每章必须新建一个实例（或调 reset）：集合跨章不清空的话，第 1 章标过「二次方资助」
    之后，后面 30 章里这个词就再也不出现触发点了。
    """

    def __init__(self, concepts: list[dict]) -> None:
        self.by_id = {c["id"]: c for c in concepts}
        self.rx, self.owner = alias_matcher(concepts)
        # 只标注参与标注的概念：aliases 为空（书里没有这个词）的不标
        self.rx, self.owner = alias_matcher(
            [c for c in concepts if c.get("mark") != "none" and c.get("aliases_zh")])
        self.marked: set[str] = set()
        self.used: set[str] = set()

    def reset(self) -> None:
        self.marked.clear()

    def wrap(self, fragment: str) -> str:
        if self.rx is None:
            return fragment
        before = len(self.marked)
        out = mark_terms(fragment, self.rx, self.owner, self.marked)
        if len(self.marked) > before:
            self.used |= {c for c in self.marked if c not in self.used}
        return out

    def cards(self) -> str:
        """本章实际被标注到的概念的卡片池（内容与 tnote 气泡池同构）。"""
        from render_html import term_cards  # 局部导入：render_html 也依赖 terms 的常量
        return term_cards([self.by_id[c] for c in sorted(self.used)],
                          prereq_index=self.by_id)


def _load_index() -> dict[str, dict[str, list[int]]]:
    if not LINE_INDEX.exists():
        return {}
    return json.loads(LINE_INDEX.read_text(encoding="utf-8")).get("chapters") or {}


def seg_at_line(index: dict, ch: int, line: int) -> str | None:
    for seg, (a, b) in (index.get(str(ch)) or {}).items():
        if a <= line < b:
            return seg
    return None


def ref_anchors(concepts: list[dict], index: dict | None = None) -> dict[str, list[dict]]:
    """把每个概念文档里的 `chapter-NN.md:行号` 换算成站点锚点。

    返回 {概念 id: [{"ch":…, "line":…, "seg":…}]}，每章只取**第一处**——
    卡片上的章号 chip 只需要一个落点。

    [设计更正] 原始设计里有一条闸门要求「497 处引用都必须落在被标注的术语上」。
    实测不成立：引用里相当一部分是**概念在那一章起了作用**、但那一行根本没写出
    这个词（例如 `26-common-knowledge` 引 `chapter-05.md:169`，那行是
    「这场军备竞赛占掉你们多少时间？」）。所以闸门改成两条：
    引用必须能解析到一个真实片段（链接完整性），以及每个参与标注的概念在全书
    至少命中一次（别名有效性）。前者管链接，后者管标注，都不越界。
    """
    index = _load_index() if index is None else index
    out: dict[str, list[dict]] = {}
    for c in concepts:
        doc = EXPLAINER_DIR / c["doc"]
        first: dict[int, tuple[int, str | None]] = {}
        if doc.exists():
            for ch_s, line_s in re.findall(r"chapter-(\d+)\.md:(\d+)",
                                           doc.read_text(encoding="utf-8")):
                ch, line = int(ch_s), int(line_s)
                if ch not in first:
                    first[ch] = (line, seg_at_line(index, ch, line))
        # weight / note 来自 terms.json 的 chapters[]，必须**合并进来**。
        # 只回 {ch,line,seg} 的话，渲染时会取不到这两个字段：weight 静默退化成
        # 默认的 "mid"（于是每章都显示「重要」，作用预估整块作废），
        # note 变成空串——而只查 href 的闸门照样放行。
        meta = {x["ch"]: x for x in c.get("chapters") or []}
        out[c["id"]] = [
            {"ch": ch, "line": ln, "seg": seg,
             "weight": (meta.get(ch) or {}).get("weight"),
             "note": (meta.get(ch) or {}).get("note")}
            for ch, (ln, seg) in sorted(first.items())]
    return out
