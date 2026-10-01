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
# 整段就是一个 URL：属数据，不属待译文本
URL_ONLY_RE = re.compile(r"(?:https?://|www\.)[^\s<>]+")
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


def load_english_words() -> set[str]:
    """词表里混进了英语词（no/to/ten/min/die…），会让「全部命中词表」失去区分力。

    词表是从 locked 片段的**全部**小写拉丁词统计来的，而这些片段里混着播报
    「MU GU GEI FA」和普通英文的机翻残留。判据必须是「整段都是泽国语」，
    不能只看「整段都在词表内」—— ten min / MU ... FO ... 会因此被误判。
    用系统词典会依赖运行环境（CI 上未必存在），因此自带一份常用词表。
    """
    wf = ROOT / "sources" / "work" / "english_words.json"
    if wf.exists():
        data = json.loads(wf.read_text(encoding="utf-8"))
        # 允许两种形态：裸数组，或 {"note":…, "words":[…]} 带说明的对象
        return set(data["words"] if isinstance(data, dict) else data)
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
    # [P0-7] 章名必须用中文数字：ch29–32 曾写成「第29章」，于是同一页里
    # 正文写「第三十章」、页内导航写「第 29 章」，目录也各写各的。
    # 判据取「章标题片段」（原文是 "Chapter NN" 的那一条）。
    for s, z in zip(src, zh):
        if re.fullmatch(r"Chapter\s+\d+", s.get("text", "") or ""):
            title = (z.get("text") or "").strip()
            m = re.fullmatch(r"第([一二三四五六七八九十百]+)章", title)
            if not m:
                errs.append(f"{s['id']}: 章名体例不一致，应为「第X章」中文数字，实际 {title!r}")
            continue
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
    english = load_english_words()
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
        # [P0-6] 译者注不得随成品上线。译者备注写在译文 JSON 的 translator_notes 里，
        # 不进正文 —— 正文里出现「译者注」是直接面向读者的编辑口吻。
        for marker in ("译者注", "译注", "編者按", "编者按", "译者按"):
            if marker in tz:
                errs.append(f"{sid}: 正文里出现译者注「{marker}」（应记入 translator_notes，"
                            f"不随成品上线）")
                break
        st, zt = tag_seq(s["text"], True), tag_seq(tz, True)
        if st != zt:
            errs.append(f"{sid}: 标签序列不一致\n    原文 {st}\n    译文 {zt}")
        # [P1-8] 泽国语必须原样保留。此前 vocab 只用来「放松」检查（把与英语功能词
        # 同形的泽国语音节从 stop_words 里去掉），从不反向校验：未标 locked 的
        # 泽国语片段可以被随意翻成中文而无人过问。这里补上反向判据。
        # 判据与 merge_terms.is_conlang_entry 一致：先剥标签，且**至少两个词**。
        # 单个词不判——No / To / min 这些英文词与人名同形于泽国语音节。
        # 还要求「至少一个词不是英语词」：词表本身混着 no/to/ten/min/die 等英语词，
        # 只判「全在词表内」会把 "ten min"、"MU ... FO ..." 误当成泽国语。
        src_conlang = strip_tags(s["text"])
        src_toks = re.findall(r"[A-Za-z]+", src_conlang)
        is_conlang_zh = (len(src_toks) >= 2 and not re.search(r"[\u3400-\u9fff]", src_conlang)
                         and all(w.lower() in vocab for w in src_toks)
                         and any(w.lower() not in english for w in src_toks))
        if is_conlang_zh:
            # 比对泽国语词本身，而不是整段文本：T6 会把 "PA GU..." 的省略号规范成「……」，
            # 那是标点体例而非翻译，逐字比整段会把正确的规范化误判成「被翻译」。
            zh_toks = re.findall(r"[A-Za-z]+", strip_tags(tz))
            if zh_toks != src_toks:
                errs.append(f"{sid}: 泽国语被改动（虚构语言必须保留罗马字原样）: "
                            f"原文 {' '.join(src_toks)[:40]} → 译文 {' '.join(zh_toks)[:40]}")
        broken = unbalanced_tags(tz)
        if broken:
            errs.append(f"{sid}: 标签未配对 {', '.join(broken)}（会破坏页面结构）")
        # [P1] 可见正文里的半角直引号：style-guide §体例要求全角「“ ”」。
        # 标签属性（<c st="…">）是样式不是引文，必须排除。
        if '"' in strip_tags(tz):
            errs.append(f"{sid}: 可见正文出现半角直引号（应为全角“”）: {strip_tags(tz)[:60]}")
        if strip_tags(tz).count("“") != strip_tags(tz).count("”"):
            errs.append(f"{sid}: 全角引号不配对（“{strip_tags(tz).count('“')} / ”"
                        f"{strip_tags(tz).count('”')}）")
        italics = sorted({n.lower() for n in re.findall(r"<([A-Za-z]+)", tz) if n.lower() in ITALIC})
        if italics:
            errs.append(f"{sid}: 中文译文不得使用斜体标记 "
                        f"{', '.join('<%s>' % n for n in italics)}（要强调请用 <b>）")
        if bold_count(tz) > emphasis_count(s["text"]):
            errs.append(f"{sid}: 加粗比原文着重还多"
                        f"（原文 {emphasis_count(s['text'])} 处，译文 {bold_count(tz)} 处）")
        if "{{S:" in tz:
            errs.append(f"{sid}: 残留占位符 {{{{S:…}}}}")
        # [P0] 空译文硬检查。判据必须是「去标签后的可见文本」：
        # tz.strip() 抓不到 "<c st=…></c> 这类只剩标签壳的形态。
        # 原文有可见文字、译文去标签后什么都没有，就是漏译。
        zh_visible = strip_tags(tz)
        src_visible = strip_tags(s["text"])
        if src_visible.strip() and not zh_visible.strip():
            errs.append(f"{sid}: 译文为空（原文有 {len(src_visible.strip())} 字可见文字，"
                        f"译文去标签后为 0）")
        body = zh_visible
        if "<" in body or ">" in body:
            errs.append(f"{sid}: 残留未转义尖括号: {body[:80]}")
        for name in {n.lower() for n in re.findall(r"<([A-Za-z]+)", tz)}:
            if name not in ALLOWED:
                errs.append(f"{sid}: 非法标签 <{name}>")
        # [P0] 拉丁词扫描必须提到「零中文」分支之外：中文段里嵌一整句英文
        # （只译了半段、或直接把英文句子留在 <c> 里）此前完全不被检查。
        scan = re.sub(r"[0-9a-fA-F]{12,}", " ", body)
        words = re.findall(r"[A-Za-z]{2,}", re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", " ", scan))
        # 只有 ≥3 字母的功能词才算「这段是英文」的证据；be/no/du 这类与泽国语音节同形的
        # 2 字母词在词表外的太多了，拿它当判据会误伤虚构语言与界面标签。
        english_veto = any(w.lower() in stop_words and len(w) >= 3 for w in words)
        # [P0] 中文段里的英文残留：整句英文此前完全不被检查（只扫「零中文」分支）。
        # 判据用「功能词密度」而不是「最长词串」：泽国语罗马字会拉长词串而功能词很少，
        # 真英文句子必然含多个功能词。阈值 3 个功能词，且要求确有汉字。
        functional = sum(1 for w in words if w.lower() in stop_words)
        if re.search(r"[\u3400-\u9fff]", body) and functional >= 3:
            snippet = " ".join(words[:12])
            errs.append(f"{sid}: 中文段内疑似残留整句英文: {snippet[:90]}")
        if not re.search(r"[\u3400-\u9fff]", body):
            # 允许：纯数字/符号；泽国语罗马字；界面英文 token / 缩写。
            # 注意不能再用「单词短就放行」——那会让整句未翻译的短词英文蒙混过关。
            # 哈希／十六进制串按「数据」看待，不参与「是否已翻译」的判定
            # （第 30 章的终端面板里有整屏的加密校验和，它们本来就该原样保留）。
            single_token = len(words) <= 1
            conlang_ok = bool(words) and all(
                w.isupper() or w.lower() in ALLOW_LATIN_WORDS or w.lower() in vocab
                or (len(w) <= 4 and (single_token or not english_veto))
                for w in words)
            symbol_ok = not words
            # 纯 URL：docstring 承诺豁免，实际此前会报「疑似未翻译」（潜伏假阳性）。
            # 网址是数据不是待译文本，与 hex 串同理。
            if not symbol_ok and URL_ONLY_RE.fullmatch(body.strip()):
                symbol_ok = True
            if not (conlang_ok or symbol_ok):
                errs.append(f"{sid}: 疑似未翻译（无中文）: {body[:90]}")
        # [P0] 连续空格规则此前被「整段任意一个 <br/>」整体关掉：
        # 一段里只要有一个换行，别的位置多打两个空格就再也不会被报。
        # 改成只看 <br/> 之间的每个非空片段。
        for piece in re.split(r"<br\s*/?>", tz, flags=re.I):
            visible_piece = strip_tags(piece)
            if re.search(r"[ \t]{2,}", visible_piece):
                errs.append(f"{sid}: 出现连续空格: {visible_piece[:60]}")
    return errs


def discover_chapters() -> list[int]:
    """全部有译文的章号。

    [回归] 原本是写死的 `range(1, 33)`：build_site 已经在第 33 章存在时正确构建，
    但本脚本的默认范围没跟上，于是**新增的章节一次都不会被校验**——
    阿拉伯数字章名、残留英文、译者注全都能从这道闸门溜过去。
    章号必须来自译文文件本身。
    """
    found = []
    for p in sorted(ZH.glob("chapter-*.zh.json")):
        m = re.search(r"chapter-(\d+)\.zh\.json$", p.name)
        if m:
            found.append(int(m.group(1)))
    return found


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or discover_chapters()
    if not todo:
        print("没有任何译文文件，未做校验")
        sys.exit(1)
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
