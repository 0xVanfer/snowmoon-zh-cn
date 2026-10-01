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


def payload(text: str, jid: str) -> str:
    """剥掉围栏与说明文字，只留文件正文。

    没有围栏时**拒绝写入**：模型在长回复里经常改用「说明 + 正文」的散文格式，
    直接落盘会把整段说明写进 style.css / reader.js，而且只有打开文件才能发现。
    """
    blocks = FENCE.findall(text)
    if not blocks:
        raise SystemExit(f"{jid}: 模型回复里没有围栏代码块，拒绝把说明文字当成文件内容写入")
    return blocks[-1].strip() + "\n"   # 正稿通常在最后一个围栏块（取最长会命中示例块）


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    recs: dict[str, dict] = {}
    for p in IN:
        if not p.exists():
            continue
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{p.name} 第 {lineno} 行无法解析：{e}")
            recs[r["id"]] = r
    missing = [jid for jids in FILES.values() for jid in jids
               if jid not in recs or not recs[jid].get("ok")]
    # 全有或全无：缺任何一个文件就一个都不写，避免「新模板 + 旧 CSS/JS」的混合前端被发布。
    # （overrides.css 是手写的集成补丁，不在这里生成，也不会被覆盖。）
    payloads: dict[str, str] = {}
    for fname, jids in FILES.items():
        if any(j in missing for j in jids):
            continue
        payloads[fname] = "".join(payload(recs[j]["text"], j) for j in jids)
    if missing:
        print(f"缺失/失败：{missing}", file=sys.stderr)
        print("未写入任何文件（缺一个即全部不写）", file=sys.stderr)
        sys.exit(1)
    # 全有或全无：**写前**已确认（缺一个就一个都不写），但**写入本身**也要原子：
    # 此前是逐个 write_text 覆盖，写完 style.css 再写 reader.js 时若进程被杀 / 抛错，
    # 留下的正是上面注释要避免的「新 CSS + 旧 JS」混合态。先全部落到 .tmp，
    # 再逐个 rename（同一文件系统内 rename 是原子的）。
    staged: list[tuple[Path, Path]] = []
    try:
        for fname in FILES:
            body = payloads[fname]
            tmp = SITE / f".{fname}.tmp"
            tmp.write_text(body, encoding="utf-8")
            staged.append((tmp, SITE / fname))
    except OSError as exc:
        for tmp, _ in staged:
            tmp.unlink(missing_ok=True)
        raise SystemExit(f"写入临时文件失败，已回滚、未改动任何目标文件：{exc}")
    for tmp, dst in staged:
        tmp.replace(dst)
    for fname in FILES:
        print(f"{'+'.join(FILES[fname])} -> pipeline/site/{fname}  "
              f"({len(payloads[fname])} 字符)")


if __name__ == "__main__":
    main()
