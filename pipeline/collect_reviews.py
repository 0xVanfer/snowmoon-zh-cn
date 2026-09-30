#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""汇总读者复核报告（reviews/*.json），生成按章的问题清单与修复任务。

用法:
    python3 pipeline/collect_reviews.py                 # 汇总统计
    python3 pipeline/collect_reviews.py --chapter 3     # 看某章全部问题
    python3 pipeline/collect_reviews.py --todo           # 生成 reviews/TODO.md（按章分组、按严重度排序）
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "reviews"
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def load() -> dict[int, list[dict]]:
    by_ch: dict[int, list[dict]] = defaultdict(list)
    for f in sorted(REVIEWS.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"! 跳过无法解析的报告 {f.name}: {e}")
            continue
        ch = data.get("chapter")
        if not isinstance(ch, int):
            print(f"! 跳过缺少整数 chapter 字段的报告 {f.name}")
            continue
        for issue in data.get("issues", []) or []:
            if not issue.get("problem"):
                issue["problem"] = ""
            issue["_reviewer"] = data.get("reviewer", f.stem)
            issue["_lens"] = data.get("lens", "?")
            by_ch[ch].append(issue)
    return by_ch


def main() -> None:
    by_ch = load()
    total = sum(len(v) for v in by_ch.values())
    sev = Counter(i.get("severity", "?") for v in by_ch.values() for i in v)
    typ = Counter(i.get("type", "?") for v in by_ch.values() for i in v)
    print(f"有问题的章 {len(by_ch)} 章，问题 {total} 条；severity={dict(sev)}")
    print("类型分布:", dict(typ.most_common()))
    if "--chapter" in sys.argv:
        ch = int(sys.argv[sys.argv.index("--chapter") + 1])
        for i in sorted(by_ch.get(ch, []), key=lambda x: SEV_ORDER.get(x.get("severity"), 9)):
            print(f"\n[{i.get('severity')}/{i.get('type')}] {i.get('id')} ({i.get('_lens')}/{i.get('_reviewer')})")
            print("  原:", (i.get("source") or "")[:200])
            print("  中:", (i.get("zh") or "")[:200])
            print("  问题:", i.get("problem"))
            print("  建议:", i.get("suggestion"))
        return
    if "--todo" in sys.argv:
        lines = ["# 复核问题待办（由 pipeline/collect_reviews.py 生成）", ""]
        for ch in sorted(by_ch):
            issues = sorted(by_ch[ch], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
            lines.append(f"## 第 {ch} 章（{len(issues)} 条）")
            lines.append("")
            for i in issues:
                lines.append(f"- [{i.get('severity')}/{i.get('type')}] `{i.get('id')}` "
                             f"{i.get('problem', '').strip()[:200]}")
                if i.get("suggestion"):
                    lines.append(f"  - 建议：{i['suggestion'].strip()[:200]}")
            lines.append("")
        (REVIEWS / "TODO.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"写入 {(REVIEWS / 'TODO.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
