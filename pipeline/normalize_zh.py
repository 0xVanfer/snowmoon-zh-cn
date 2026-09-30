#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""中文译文规范化：术语统一 + 空格/标点体例统一。

在译文 JSON 上就地规范化（保留原文件备份到 sources/work/backup/）。
只处理非 locked 片段的标签之外文本。

规则（依据 docs/research/ 两份调研 + docs/style-guide.md）：
  T1 术语别名替换：把已知的异体译名替换为术语表规范译名；
  T2 连续空格压成一个；
  T3 中西文之间统一一个半角空格（CJK↔数字、CJK↔≥2 个拉丁字母）；
  T4 中文与西文标点之间不留空格；
  T5 中文语境里的半角标点改全角（，。！？：；）；
  T6 三个以上英文句点 → ……；
  T7 行内不应出现的空白（如 "</c> ，" 之类）整理。

用法: python3 pipeline/normalize_zh.py [章节号...]
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZH = ROOT / "translations" / "zh"
BACKUP = ROOT / "sources" / "work" / "backup"
GLOSSARY = ROOT / "pipeline" / "glossary.json"

CJK = r"\u3400-\u9fff\u3000-\u303f\uff01-\uff60"
HAN = r"\u3400-\u9fff"
TAG_SPLIT = re.compile(r"(<[^>]+>)")


def load_aliases() -> dict[str, str]:
    glos = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    alias: dict[str, str] = {}
    for e in glos["entries"]:
        for a in e.get("aliases", []) or []:
            alias[a] = e["zh"]
    for a, canon in (glos.get("aliases") or {}).items():
        alias[a] = canon
    # 长键优先：否则「掌舵团」会被较短的「掌舵」先替换掉，
    # 结果依赖术语表 JSON 的键序——重排一次键就静默改了正文。
    return dict(sorted(alias.items(), key=lambda kv: (-len(kv[0]), kv[0])))


def load_fixups() -> dict[str, list]:
    p = ROOT / "pipeline" / "fixups.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def apply_fixups(t: str, rules: list) -> str:
    for pat, rep in rules:
        t = re.sub(pat, rep, t)
    return t


def fix_text(t: str, alias: dict[str, str]) -> str:
    for bad, good in alias.items():
        if bad and bad in t:
            t = t.replace(bad, good)
    # T6 英文省略号 → 中文省略号（数字区间 0...199 不动）
    t = re.sub(r"(?<!\d)\.{3,}(?!\d)", "……", t)
    t = re.sub(r"(?<=[\u4e00-\u9fff])\.\.(?=[\u4e00-\u9fff])", "……", t)
    # T2 连续空格
    t = re.sub(r"[ \t]{2,}", " ", t)
    # T4 中文标点前后不留空格
    t = re.sub(rf"\s+(?=[，。！？；：、）】》”’])", "", t)
    t = re.sub(rf"(?<=[（【《“‘])\s+", "", t)
    # T5 中文语境半角标点 → 全角
    t = re.sub(rf"(?<=[{CJK}]),(?=[{CJK}])", "，", t)
    t = re.sub(rf"(?<=[{CJK}]);(?=[{CJK}])", "；", t)
    t = re.sub(rf"(?<=[{CJK}]):(?=[{CJK}])", "：", t)
    t = re.sub(rf"(?<=[{CJK}])\?(?=[{CJK}“”]|$)", "？", t)
    t = re.sub(rf"(?<=[{CJK}])!(?=[{CJK}“”]|$)", "！", t)
    t = re.sub(rf"(?<=[{CJK}])\.(?=$|[{CJK}“”])", "。", t)
    # T3 空格体例：拉丁词与「含字母的混合 token」（CO2 / 0x18f4 / 5G / TEI）与汉字之间，
    #    统一一个半角空格；纯数字与汉字之间不留空格（3724年雪月3日、约2公里、掉3分）。
    #    注意必须整 token 判断：只看前一位会把「CO2 和」压成「CO2和」。
    #   token 允许含 . - _ / %（PM2.5、0x18f4...60c5、A/B）；先把「字母+空格+数字」
    #   这类内部含空格的 token（TEI 70000）保护起来，避免被当成「数字贴汉字」压掉空格。
    MARK = "\u0001"
    t = re.sub(r"([A-Za-z]+) (\d+)", lambda m: m.group(1) + MARK + m.group(2), t)
    TOKEN = "[0-9A-Za-z][0-9A-Za-z.\\-_/%\u0001]*"

    def _tok_before_cjk(m: re.Match) -> str:
        tok = m.group(1)
        return (tok + " " if re.search(r"[A-Za-z]", tok) else tok) + m.group(2)

    t = re.sub(rf"({TOKEN}) *([{HAN}])", _tok_before_cjk, t)

    def _cjk_before_tok(m: re.Match) -> str:
        tok = m.group(2)
        return m.group(1) + (" " if re.search(r"[A-Za-z]", tok) else "") + tok

    t = re.sub(rf"([{HAN}]) *({TOKEN})", _cjk_before_tok, t)
    t = t.replace(MARK, " ")
    # T3a 中英混排的引号/括号内不留首尾空格
    t = re.sub(r"([“（《])\s+", r"\1", t)
    t = re.sub(r"\s+([”）》])", r"\1", t)
    # T3b 百分比/单位与数字之间不留空格
    t = re.sub(r"(?<=\d)\s+(?=%|℃|°|‰)", "", t)
    # T2b 再次压缩可能产生的新空格
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = t.strip()
    return t


TOKEN_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.\-_/%]*")


def _needs_space(token: str) -> bool:
    return bool(re.search(r"[A-Za-z]", token))


def fix_segment(text: str, alias: dict[str, str], fixups: list | None = None) -> str:
    text = re.sub(r"(?<=[0-9A-Za-z]) +</(sub|sup|e|b|i|c|code|f)>", r"</\1>", text)
    # 历史遗留：空格被塞进行内标签开头（「叫<e> dzu…」）→ 挪到标签之前
    text = re.sub(r"([\u3400-\u9fff])(<[a-z]+(?: [^>]*)?>) +(?=[0-9A-Za-z])", r"\1 \2", text)
    parts = TAG_SPLIT.split(text)
    protected = 0       # <code>/<f> 的内容是字面量／虚构语言，不得做标点空格体例处理
    for i, p in enumerate(parts):
        if i % 2:
            m = re.match(r"</?([A-Za-z]+)", p)
            tag = m.group(1).lower() if m else ""
            if tag in ("code", "f"):
                protected += -1 if p.startswith("</") else 1
            continue
        if protected > 0:
            continue
        seg = fix_text(p, alias)
        if fixups:
            seg = apply_fixups(seg, fixups)
        parts[i] = seg
    # 跨标签边界补空格：中文↔拉丁/混合 token 被 <e>、<c>、<f>、<sub> 等切开时，
    # 逐段规范化看不到边界，这里对相邻文本段做一次修补（左侧取「忽略标签后的可见文字」，
    # 这样 CO<sub>2</sub>读数 也能识别出 CO2 这个 token）。
    text_idx = [i for i in range(0, len(parts), 2)]
    for b in text_idx[1:]:
        left = "".join(parts[j] for j in text_idx if j < b)
        right = parts[b]
        if not left or not right:
            continue
        if re.search(r"[\u3400-\u9fff]$", left):
            m = TOKEN_RE.match(right)
            if m and _needs_space(m.group(0)) and not right.startswith(" "):
                parts[b] = " " + right
        elif re.search(r"[0-9A-Za-z.\-_/%]$", left):
            toks = list(TOKEN_RE.finditer(left))
            if toks and re.match(r"[\u3400-\u9fff]", right) and not left.endswith(" "):
                if _needs_space(toks[-1].group(0)):
                    parts[b] = " " + right
    return "".join(parts)


def main() -> None:
    todo = []
    for x in sys.argv[1:]:
        if not x.isdigit():
            raise SystemExit(f"章节号必须是数字：{x!r}")
        todo.append(int(x))
    todo = todo or list(range(1, 33))
    alias = load_aliases()
    fixups_all = load_fixups()
    BACKUP.mkdir(parents=True, exist_ok=True)
    for ch in todo:
        p = ZH / f"chapter-{ch:02d}.zh.json"
        if not p.exists():
            print(f"ch{ch:02d}: 无译文，跳过")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        src = {s["id"]: s for s in json.loads(
            (ROOT / "sources" / "work" / "segments" / f"chapter-{ch:02d}.src.json")
            .read_text(encoding="utf-8"))["segments"]}
        changed = 0
        for seg in data["segments"]:
            if src.get(seg["id"], {}).get("locked"):
                continue
            new = fix_segment(seg["text"], alias, fixups_all.get(f"chapter-{ch:02d}"))
            if new != seg["text"]:
                seg["text"] = new
                changed += 1
        if changed:
            # 备份只留「第一次改动之前」的版本：反复运行不得覆盖掉真正的原始文本
            bak = BACKUP / p.name
            if not bak.exists():
                shutil.copy2(p, bak)
            # 原子写：中途崩溃不会留下半个 JSON
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(p)
        print(f"ch{ch:02d}: 规范化 {changed} 条片段")


if __name__ == "__main__":
    main()
