#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""把视觉模型产出的前端文件从 JSONL 里取出来，拼装并落到 pipeline/site/。

视觉模型的输出是「一段说明 + 一个围栏代码块」，这里剥掉围栏与说明，只留文件正文；
大文件（`style.css`、`reader.js`）由多次调用分段产出，按固定顺序拼接。

JSONL 由以下命令生成（网关 120 秒超时，所以必须分段）：

    python3 pipeline/vision_api.py --batch sources/work/design/jobs.jsonl \
        --out sources/work/design/out.jsonl --concurrency 5
    python3 pipeline/vision_api.py --batch sources/work/design/jobs2.jsonl \
        --out sources/work/design/out2.jsonl --concurrency 4

用法: python3 pipeline/extract_design_files.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN = [ROOT / "sources" / "work" / "design" / "out.jsonl",
      ROOT / "sources" / "work" / "design" / "out2.jsonl"]
SITE = ROOT / "pipeline" / "site"

# 落盘文件名 -> 按顺序拼接的 job id
FILES = {
    "style.css": ["site-css-1", "site-css-2", "site-css-3", "site-css-4"],
    "reader.js": ["site-js-1", "site-js-2", "site-js-3"],
    "index.html": ["site-index"],
    "toc.html": ["site-toc"],
    "chapter.html": ["site-chapter"],
}
FENCE = re.compile(r"```[a-zA-Z]*\s*\n(.*?)```", re.S)


def payload(text: str) -> str:
    """剥掉围栏与说明文字，只留文件正文。"""
    blocks = FENCE.findall(text)
    if not blocks:
        return text.strip() + "\n"
    return max(blocks, key=len).strip() + "\n"


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    recs: dict[str, dict] = {}
    for p in IN:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                recs[r["id"]] = r
    missing = [jid for jids in FILES.values() for jid in jids
               if jid not in recs or not recs[jid].get("ok")]
    for fname, jids in FILES.items():
        if any(j in missing for j in jids):
            continue
        body = "".join(payload(recs[j]["text"]) for j in jids)
        (SITE / fname).write_text(body, encoding="utf-8")
        print(f"{'+'.join(jids)} -> pipeline/site/{fname}  ({len(body)} 字符)")
    if missing:
        print(f"缺失/失败：{missing}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
