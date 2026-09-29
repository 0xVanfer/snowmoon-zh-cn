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
    return alias


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
    # T3 空格体例：拉丁词（≥2 字母）与汉字之间加一个半角空格；
    #    数字与汉字之间不留空格（中文出版惯例：3724年雪月3日、约2公里、掉3分），
    #    但形如 0x18f4、5G 这类含字母的混合 token 仍与汉字分开。
    t = re.sub(rf"([{HAN}]) *(\d+)(?![0-9A-Za-z])", r"\1\2", t)
    t = re.sub(rf"(?<=\d) *([{HAN}])", r"\1", t)
    t = re.sub(rf"([{HAN}])([0-9]*[A-Za-z][A-Za-z]{{1,}})", r"\1 \2", t)
    t = re.sub(rf"([A-Za-z]{{2,}})([{HAN}])", r"\1 \2", t)
    t = re.sub(rf"([{HAN}])(0x[0-9A-Fa-f]+)", r"\1 \2", t)
    # T3a 中英混排的引号/括号内不留首尾空格
    t = re.sub(r"([“（《])\s+", r"\1", t)
    t = re.sub(r"\s+([”）》])", r"\1", t)
    # T3b 百分比/单位与数字之间不留空格
    t = re.sub(r"(?<=\d)\s+(?=%|℃|°|‰)", "", t)
    # T2b 再次压缩可能产生的新空格
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = t.strip()
    return t


def fix_segment(text: str, alias: dict[str, str], fixups: list | None = None) -> str:
    parts = TAG_SPLIT.split(text)
    out = []
    for i, p in enumerate(parts):
        if i % 2:
            out.append(p)
        else:
            seg = fix_text(p, alias)
            if fixups:
                seg = apply_fixups(seg, fixups)
            out.append(seg)
    return "".join(out)


def main() -> None:
    todo = [int(x) for x in sys.argv[1:]] or list(range(1, 33))
    alias = load_aliases()
    fixups_all = load_fixups()
    BACKUP.mkdir(parents=True, exist_ok=True)
    for ch in todo:
        p = ZH / f"chapter-{ch:02d}.zh.json"
        if not p.exists():
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
            shutil.copy2(p, BACKUP / p.name)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"ch{ch:02d}: 规范化 {changed} 条片段")


if __name__ == "__main__":
    main()
