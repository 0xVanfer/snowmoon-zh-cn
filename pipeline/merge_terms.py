#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把各章译文里的 new_terms 合并回术语表（唯一事实源），并生成 docs/glossary.md。

用法:
    python3 pipeline/merge_terms.py            # 合并 + 生成文档
    python3 pipeline/merge_terms.py --check     # 只报告冲突，不写文件
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "pipeline" / "glossary.json"
ZH = ROOT / "translations" / "zh"
DOC = ROOT / "docs" / "glossary.md"

KIND_ORDER = ["person", "place", "org", "tech", "term", "unit", "month", "inflection", "conlang"]

# 泽国语条目的中文值只可能是空或这类占位说明；一旦写出实义中文，它就是普通译文
CONLANG_ZH_PLACEHOLDER_RE = re.compile(r"^$|^[（(]?\s*(?:保留罗马字|保留原文|音译|不译)[^）)]*[）)]?$")
# 时间单位译名：读者需要它作读音提示，不算「已翻译成中文」
SOUND_ONLY_ZH = re.compile(r"^[零一二三四五六七八九十百千万两]*\s*(?:嘀嗒|提克)$")


def is_conlang_entry(en: str, zh: str) -> bool:
    """术语表里登记的虚构语言（泽国语罗马字）：只作理解参考，正文必须保留罗马字原样。

    判定要求**至少两个词**且全部在词表内。单词一律不判：
    No / To / pin / TEI 这些英文词与人名词都与泽国语音节同形，
    一旦把 `No → 反对`（表决按钮）判成虚构语言，就会反过来要求正文保留英文。
    也不认「全大写」——CPU/GUI 这类缩写不是泽国语。

    [P1] `zh` 原本是死参数：已译成中文的英文短语（`she can` → 「她能」）只要词形
    撞上词表就会被判成虚构语言，并在 docs/glossary.md 里发布成
    「不得译成中文」——与它自己的中文值直接矛盾。
    判据很简单：**中文值里出现实义词，一律不是泽国语**。
    只有「空」或「（保留罗马字）」这类占位说明才算泽国语。
    `MU GU GEI FA → 五十嘀嗒` 是唯一例外：它由显式 kind 声明（见 main），
    且「嘀嗒」是本书的时间单位译名，读者需要它作读音提示。
    """
    zh = (zh or "").strip()
    if re.search(r"[\u3400-\u9fff]", zh) and not CONLANG_ZH_PLACEHOLDER_RE.match(zh) \
            and not SOUND_ONLY_ZH.match(zh):
        return False
    vf = ROOT / "sources" / "work" / "conlang_vocab.json"
    vocab = set(json.loads(vf.read_text(encoding="utf-8"))) if vf.exists() else set()
    words = re.findall(r"[a-zA-Z]+", en)
    if len(words) < 2 or not vocab:
        return False
    return all(w.lower() in vocab for w in words)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="只报告冲突，不写文件；有冲突或未合并的新术语时退出码非 0")
    args = ap.parse_args(argv)
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
            # 译者显式声明 kind=conlang 是权威信号，不受中文值影响：
            # `MU GU GEI FA → 五十嘀嗒` 是泽国语播报，但读者需要「嘀嗒」这个读音提示。
            if kind == "conlang" or is_conlang_entry(en, zh):
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
    # 既有条目重新分类：全部是泽国语音节的「术语」实为虚构语言（单词、多词都算）
    for e in glos["entries"]:
        if e.get("kind") == "term" and is_conlang_entry(e["en"], e.get("zh", "")):
            e["kind"] = "conlang"
            if not (e.get("note") or "").startswith("（虚构语言"):
                e["note"] = "（虚构语言：正文保留罗马字原样，不得译成中文；此条仅供理解）" + (e.get("note") or "")
    if args.check:
        # [P1] --check 对「有新增术语未合并」原本返回 0：CI 会以为一切正常，
        # 而术语表其实已经落后于译文。两种未合并都必须让闸门变红。
        if conflicts or added:
            if added:
                print(f"  还有 {len(added)} 条新术语未并入 glossary.json"
                      f"（跑 merge_terms.py 合并）")
            sys.exit(1)
        return
    glos["entries"].sort(key=lambda e: (KIND_ORDER.index(e["kind"]) if e.get("kind") in KIND_ORDER else 99,
                                        e["en"].lower()))
    GLOSSARY.write_text(json.dumps(glos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    render_doc(glos)
    # 术语冲突必须让调用方看得见：退出码是唯一的机器可读信号
    if conflicts:
        sys.exit(1)


def render_doc(glos: dict) -> None:
    lines = ["# Snowmoon 中译术语表", "",
             "> 本文件由 `pipeline/merge_terms.py` 的 `render_doc()` 从 "
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
    # 未知参数必须报错：此前 `--chek` 会被静默忽略、脚本照常写盘，
    # 「只想看看有没有冲突」的意图被当成「合并并发布」。
    main(sys.argv[1:])
