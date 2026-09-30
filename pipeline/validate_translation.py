#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""译文自检：结构一致性校验。

对照 sources/work/segments/chapter-NN.src.json 与 translations/zh/chapter-NN.zh.json：
  1. 片段 id 集合与顺序完全一致；
  2. locked 片段必须逐字不变（虚构语言不得翻译）；
  3. mini-markup 标签序列（含属性）完全一致，杜绝丢标签/改样式/丢颜色；
  4. 不得残留非法标签、未转义的尖括号、{{S:}} 占位符；
  5. 目标文本必须含中文（除 locked、纯数字/符号/URL/界面 token 外）。

  [用户请求] 中文不用斜体：中文译文**禁止** `<e>`/`<i>`；原文的 `<e>`（着重）允许取消或用 `<b>`
  顶替，因此着重标记不参与第 3 条的结构比对，另按「加粗数不得超过原文着重数」把关。

用法: python3 pipeline/validate_translation.py [章节号...]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "sources" / "work" / "segments"
ZH = ROOT / "translations" / "zh"

TAG_RE = re.compile(r"<(/?)([A-Za-z]+)([^>]*?)(/?)>")
ALLOWED = {"c", "b", "i", "e", "sup", "sub", "code", "a", "br", "f", "u", "small", "mark"}
# [用户请求] 中文不用斜体：这些标记在中文译文里一律作废；<e> 允许被 <b> 顶替
ITALIC = {"e", "i"}
EMPHASIS = {"e", "i", "b", "em", "strong"}
# 允许保留的英文 token（界面/技术缩写），以及非泽国语但同样原样保留的短词
ALLOW_LATIN_WORDS = {"ai", "api", "gui", "llm", "url", "id", "pm", "tei", "tau", "gph", "du", "vnu",
                     "shi", "gei", "xor", "kag", "ziu", "uvc", "fa", "le", "bi", "ze", "ha", "co",
                     "gu", "mu", "agi", "pdf", "html", "css", "svg", "kg", "km", "cm", "mm"}
# 英语功能词：出现即说明这段是「没翻译的英文」而不是泽国语罗马字。
# 与泽国语词表同形的（no/go/du/fa…）在运行时扣除，避免误伤真正的虚构语言。
COMMON_ENGLISH = {
    "about", "after", "all", "also", "and", "any", "are", "as", "at", "be", "because", "been",
    "before", "between", "both", "but", "by", "can", "could", "did", "do", "does", "each", "for",
    "from", "get", "got", "had", "has", "have", "he", "her", "here", "him", "his", "how", "if",
    "in", "into", "is", "it", "its", "just", "may", "me", "might", "more", "most", "must", "my",
    "no", "not", "now", "of", "on", "one", "only", "or", "other", "our", "out", "over", "own",
    "said", "same", "say", "see", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those", "to", "too", "two", "up",
    "us", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "why",
    "will", "with", "would", "you", "your",
}


def load_conlang_vocab() -> set[str]:
    vf = ROOT / "sources" / "work" / "conlang_vocab.json"
    if vf.exists():
        return set(json.loads(vf.read_text(encoding="utf-8")))
    return set()


def tag_seq(s: str, drop_emphasis: bool = False) -> list[str]:
    out = []
    for m in TAG_RE.finditer(s):
        closing, name, attrs, selfclose = m.groups()
        name = name.lower()
        if drop_emphasis and name in EMPHASIS:
            continue
        out.append(f"{'/' if closing else ''}{name}{attrs.strip()}{'/' if selfclose else ''}")
    return out


def emphasis_count(s: str) -> int:
    """开标签数：原文的着重（含 `<b>`），用于限制译文加粗的规模。"""
    return len(re.findall(r"<(?:e|i|b|em|strong)(?:\s[^>]*)?>", s, re.I))


def bold_count(s: str) -> int:
    return len(re.findall(r"<b(?:\s[^>]*)?>", s, re.I))


def unbalanced_tags(s: str) -> list[str]:
    """强调类标签必须成对：翻译时漏掉一个 </b> 会把外层 <span> 提前闭合，静默毁掉排版。"""
    bad = []
    for tag in ("b", "e", "i", "em", "strong", "c", "f", "code", "a", "sup", "sub", "u", "small", "mark"):
        opens = len(re.findall(rf"<{tag}(?:\s[^>]*)?>", s, re.I))
        closes = len(re.findall(rf"</{tag}\s*>", s, re.I))
        if opens != closes:
            bad.append(f"<{tag}> {opens}/{closes}")
    return bad


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    return TAG_RE.sub("", s)


def check(chapter: int) -> list[str]:
    errs: list[str] = []
    src_p = WORK / f"chapter-{chapter:02d}.src.json"
    zh_p = ZH / f"chapter-{chapter:02d}.zh.json"
    if not zh_p.exists():
        return [f"缺失译文文件 {zh_p.relative_to(ROOT)}"]
    if not src_p.exists():
        return [f"缺失原文片段文件 {src_p.relative_to(ROOT)}"]
    src = json.loads(src_p.read_text(encoding="utf-8"))["segments"]
    try:
        data = json.loads(zh_p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"JSON 解析失败: {e}"]
    zh = data.get("segments") or []
    if [s["id"] for s in src] != [s.get("id") for s in zh]:
        errs.append("片段 id 序列与原文不一致")
        miss = [s["id"] for s in src if s["id"] not in {z.get("id") for z in zh}]
        extra = [z.get("id") for z in zh if z.get("id") not in {s["id"] for s in src}]
        if miss:
            errs.append(f"  缺失 {len(miss)} 条: {miss[:8]}")
        if extra:
            errs.append(f"  多余 {len(extra)} 条: {extra[:8]}")
        return errs
    vocab = load_conlang_vocab()
    stop_words = {w for w in COMMON_ENGLISH if w not in vocab}
    for s, z in zip(src, zh):
        sid = s["id"]
        tz = z.get("text")
        if not isinstance(tz, str):
            errs.append(f"{sid}: text 不是字符串")
            continue
        if s["locked"]:
            if tz != s["text"]:
                errs.append(f"{sid}: locked 片段被改动（虚构语言必须原样保留）")
            continue
        st, zt = tag_seq(s["text"], True), tag_seq(tz, True)
        if st != zt:
            errs.append(f"{sid}: 标签序列不一致\n    原文 {st}\n    译文 {zt}")
        broken = unbalanced_tags(tz)
        if broken:
            errs.append(f"{sid}: 标签未配对 {', '.join(broken)}（会破坏页面结构）")
        italics = sorted({n.lower() for n in re.findall(r"<([A-Za-z]+)", tz) if n.lower() in ITALIC})
        if italics:
            errs.append(f"{sid}: 中文译文不得使用斜体标记 "
                        f"{', '.join('<%s>' % n for n in italics)}（要强调请用 <b>）")
        if bold_count(tz) > emphasis_count(s["text"]):
            errs.append(f"{sid}: 加粗比原文着重还多"
                        f"（原文 {emphasis_count(s['text'])} 处，译文 {bold_count(tz)} 处）")
        if "{{S:" in tz:
            errs.append(f"{sid}: 残留占位符 {{{{S:…}}}}")
        body = strip_tags(tz)
        if "<" in body or ">" in body:
            errs.append(f"{sid}: 残留未转义尖括号: {body[:80]}")
        for name in {n.lower() for n in re.findall(r"<([A-Za-z]+)", tz)}:
            if name not in ALLOWED:
                errs.append(f"{sid}: 非法标签 <{name}>")
        if not re.search(r"[\u3400-\u9fff]", body):
            # 允许：纯数字/符号；泽国语罗马字；界面英文 token / 缩写。
            # 注意不能再用「单词短就放行」——那会让整句未翻译的短词英文蒙混过关。
            # 哈希／十六进制串按「数据」看待，不参与「是否已翻译」的判定
            # （第 30 章的终端面板里有整屏的加密校验和，它们本来就该原样保留）。
            scan = re.sub(r"[0-9a-fA-F]{12,}", " ", body)
            words = re.findall(r"[A-Za-z]{2,}", re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", " ", scan))
            # 只有 ≥3 字母的功能词才算「这段是英文」的证据；be/no/du 这类与泽国语音节同形的
            # 2 字母词在词表外的太多了，拿它当判据会误伤虚构语言与界面标签。
            english_veto = any(w.lower() in stop_words and len(w) >= 3 for w in words)
            single_token = len(words) <= 1
            conlang_ok = bool(words) and all(
                w.isupper() or w.lower() in ALLOW_LATIN_WORDS or w.lower() in vocab
                or (len(w) <= 4 and (single_token or not english_veto))
                for w in words)
            symbol_ok = not words
            if not (conlang_ok or symbol_ok):
                errs.append(f"{sid}: 疑似未翻译（无中文）: {body[:90]}")
        if re.search(r"\s{2,}", body) and not re.search(r"<br\s*/?>", tz, re.I):
            errs.append(f"{sid}: 出现连续空格: {body[:60]}")
    return errs


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    bad = 0
    for ch in todo:
        errs = check(ch)
        if errs:
            bad += 1
            print(f"FAIL ch{ch:02d} ({len(errs)} 处)")
            for e in errs[:12]:
                print("   -", e)
        else:
            print(f"OK   ch{ch:02d}")
    print("失败章节数:", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
