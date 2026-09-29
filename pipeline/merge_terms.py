#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把各章译文里的 new_terms 合并回术语表（唯一事实源），并生成 docs/glossary.md。

用法:
    python3 pipeline/merge_terms.py            # 合并 + 生成文档
    python3 pipeline/merge_terms.py --check     # 只报告冲突，不写文件
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "pipeline" / "glossary.json"
ZH = ROOT / "translations" / "zh"
DOC = ROOT / "docs" / "glossary.md"

KIND_ORDER = ["person", "place", "org", "tech", "term", "unit", "month", "inflection", "conlang"]


def is_conlang_entry(en: str, zh: str) -> bool:
    """术语表里登记的虚构语言（泽国语罗马字）：只作理解参考，正文必须保留罗马字原样。"""
    vf = ROOT / "sources" / "work" / "conlang_vocab.json"
    vocab = set(json.loads(vf.read_text(encoding="utf-8"))) if vf.exists() else set()
    words = re.findall(r"[a-zA-Z]+", en)
    if not words or not vocab:
        return False
    if all(w.lower() in vocab or w.isupper() for w in words):
        return True
    return False


def main() -> None:
    check_only = "--check" in sys.argv
    glos = json.loads(GLOSSARY.read_text(encoding="utf-8"))
    have = {e["en"]: e for e in glos["entries"]}
    added, conflicts = [], []
    for f in sorted(ZH.glob("chapter-*.zh.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for t in data.get("new_terms") or []:
            en, zh = t.get("en", "").strip(), t.get("zh", "").strip()
            if not en or not zh:
                continue
            if en in have:
                if have[en]["zh"] != zh:
                    conflicts.append((f.stem, en, have[en]["zh"], zh, have[en].get("kind", "")))
                continue
            kind = t.get("kind", "term")
            note = t.get("note", "")
            if is_conlang_entry(en, zh):
                kind = "conlang"
                note = "（虚构语言：正文保留罗马字原样，不得译成中文；此条仅供理解）" + note
            entry = {"en": en, "zh": zh, "kind": kind, "note": note, "from": f.stem}
            glos["entries"].append(entry)
            have[en] = entry
            added.append((en, zh))
    print(f"新增术语 {len(added)} 条；与既有术语冲突 {len(conflicts)} 条")
    for a in added:
        print("  +", a[0], "→", a[1])
    for c in conflicts:
        print(f"  ! {c[0]}: {c[1]} 既有「{c[2]}」 vs 本章「{c[3]}」")
    # 既有条目重新分类：多词且全部是泽国语音节的「术语」实为虚构语言
    for e in glos["entries"]:
        if e.get("kind") == "term" and " " in e["en"] and is_conlang_entry(e["en"], e.get("zh", "")):
            e["kind"] = "conlang"
            if not (e.get("note") or "").startswith("（虚构语言"):
                e["note"] = "（虚构语言：正文保留罗马字原样，不得译成中文；此条仅供理解）" + (e.get("note") or "")
    if check_only:
        return
    glos["entries"].sort(key=lambda e: (KIND_ORDER.index(e["kind"]) if e.get("kind") in KIND_ORDER else 99,
                                        e["en"].lower()))
    GLOSSARY.write_text(json.dumps(glos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    render_doc(glos)


def render_doc(glos: dict) -> None:
    lines = ["# Snowmoon 中译术语表", "",
             "> 本文件由 `pipeline/render_glossary.py`（`merge_terms.py` 内置）从 "
             "[`pipeline/glossary.json`](../pipeline/glossary.json) 生成，请勿手工编辑；",
             "> 修改请改 JSON 后重跑脚本。", "", "## 命名与翻译政策", ""]
    for p in glos["policies"]:
        lines.append(f"- {p}")
    lines += ["", "## 月份与日期", "",
              "| 原文 | 中文 |", "| --- | --- |"]
    for en, zh in glos["months"].items():
        lines.append(f"| {en} | {zh} |")
    lines += ["", f"日期格式：`{glos['date_format']}`；章节标题：`{glos['title_format']}`。", "",
              "## 条目", "", "| 原文 | 中文 | 类别 | 备注 |", "| --- | --- | --- | --- |"]
    for e in glos["entries"]:
        note = (e.get("note") or "").replace("|", "／")
        lines.append(f"| {e['en']} | {e['zh']} | {e.get('kind', '')} | {note} |")
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已写入 {GLOSSARY.relative_to(ROOT)} 与 {DOC.relative_to(ROOT)}；"
          f"共 {len(glos['entries'])} 条")


if __name__ == "__main__":
    main()
