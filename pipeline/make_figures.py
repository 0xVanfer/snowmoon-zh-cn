#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""插图中文版生成流水线（视觉模型）。

两步式，便于断点续跑：
    python3 pipeline/make_figures.py build            # 生成 jobs JSONL
    python3 pipeline/vision_api.py --batch sources/work/jobs/figures.jsonl \
        --out sources/work/jobs/figures.out.jsonl --concurrency 6
    python3 pipeline/make_figures.py apply            # 解析 + 校验 + 落盘 + manifest

产物：
    book/images/chapter-NN-fig-MM.svg     中文版插图
    sources/work/figures/manifest.json    图注、来源、校验状态
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "sources" / "work" / "figures"
CHAP_DIR = ROOT / "sources" / "work" / "chapters"
SEG_DIR = ROOT / "sources" / "work" / "segments"
ZH_DIR = ROOT / "translations" / "zh"
JOB_DIR = ROOT / "sources" / "work" / "jobs"
BOOK_IMG = ROOT / "book" / "images"
PROMPT = ROOT / "pipeline" / "prompts" / "svg-zh.md"
GLOSSARY = ROOT / "pipeline" / "glossary.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_svg import validate  # noqa: E402


def load_glossary() -> dict:
    return json.loads(GLOSSARY.read_text(encoding="utf-8"))


def chapter_of(name: str) -> int:
    return int(re.search(r"chapter-(\d+)-fig", name).group(1))


def build() -> None:
    spec = PROMPT.read_text(encoding="utf-8")
    glos = load_glossary()
    terms = {e["en"]: e["zh"] for e in glos["entries"]}
    months = glos["months"]
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for svg_path in sorted(FIG_DIR.glob("*.svg")):
        name = svg_path.name
        ch = chapter_of(name)
        svg = svg_path.read_text(encoding="utf-8")
        # 术语子集：出现在本图中的术语 + 月份名
        subset = {k: v for k, v in terms.items() if re.search(r"\b" + re.escape(k) + r"\b", svg, re.I)}
        for m, zh in months.items():
            if re.search(m, svg, re.I):
                subset[m] = zh
        # 上下文：图中文字 + 前后段落
        chap = json.loads((CHAP_DIR / f"chapter-{ch:02d}.json").read_text(encoding="utf-8"))
        src_segs = {s["id"]: s["text"] for s in json.loads(
            (SEG_DIR / f"chapter-{ch:02d}.src.json").read_text(encoding="utf-8"))["segments"]}
        zh_segs = {}
        zh_file = ZH_DIR / f"chapter-{ch:02d}.zh.json"
        if zh_file.exists():
            zh_segs = {s["id"]: s["text"] for s in json.loads(
                zh_file.read_text(encoding="utf-8"))["segments"]}
        ctx_lines: list[str] = []
        prev_ids: list[str] = []
        for blk in chap["blocks"]:
            if blk.get("kind") == "figure" and name in blk.get("figures", []):
                for sid in reversed(prev_ids[-2:]):
                    ctx_lines.append(f"[前文英] {src_segs.get(sid, '')}")
                    if zh_segs.get(sid):
                        ctx_lines.append(f"[前文中] {zh_segs[sid]}")
                break
            prev_ids = [s for s in blk.get("segs", []) if s in src_segs]
        caption_hint = "（此处没有文字，请原样保留图形并给出中文图注）" if "<text" not in svg else ""
        prompt = f"""{spec}

## 术语表（必须一致）

{json.dumps(subset, ensure_ascii=False, indent=1)}

## 本图上下文

{chr(10).join(ctx_lines) if ctx_lines else "（无）"}
{caption_hint}

## 待改写的 SVG（文件名 {name}）

{svg}
"""
        jobs.append({"id": name[:-4], "prompt": prompt, "max_tokens": min(32000, 4000 + 2 * len(svg))})
    out = JOB_DIR / "figures.jsonl"
    out.write_text("\n".join(json.dumps(j, ensure_ascii=False) for j in jobs) + "\n", encoding="utf-8")
    print(f"jobs: {len(jobs)} → {out.relative_to(ROOT)}")


def apply_results(results: Path) -> None:
    BOOK_IMG.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if (FIG_DIR / "manifest.json").exists():
        manifest = json.loads((FIG_DIR / "manifest.json").read_text(encoding="utf-8"))
    ok = fail = 0
    for line in results.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        name = rec["id"]
        target = BOOK_IMG / f"{name}.svg"
        if not rec.get("ok"):
            fail += 1
            manifest[name] = {"status": "error", "error": rec.get("error", "")[:300]}
            print(f"FAIL {name}: {rec.get('error', '')[:120]}")
            continue
        text = rec["text"]
        m = re.search(r"CAPTION:\s*(.+)", text)
        caption = m.group(1).strip() if m else ""
        m2 = re.search(r"<svg\b.*</svg>", text, re.S)
        if not m2:
            fail += 1
            manifest[name] = {"status": "error", "error": "输出中没有完整 <svg>"}
            print(f"FAIL {name}: 无 SVG")
            continue
        svg = m2.group(0).strip()
        target.write_text(svg + "\n", encoding="utf-8")
        errs = validate(FIG_DIR / f"{name}.svg", target)
        status = "ok" if not errs else "invalid"
        manifest[name] = {"status": status, "caption": caption, "errors": errs[:8],
                          "chars": len(svg)}
        if errs:
            fail += 1
            print(f"INVALID {name}: {errs[0][:140]}")
        else:
            ok += 1
            print(f"OK {name}  caption={caption}")
    (FIG_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"生成 {ok} 张合格中文插图，{fail} 张待修")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "build":
        build()
    elif mode == "apply":
        src = Path(sys.argv[2]) if len(sys.argv) > 2 else JOB_DIR / "figures.out.jsonl"
        apply_results(src)
    else:
        raise SystemExit("用法: make_figures.py build|apply [results.jsonl]")


if __name__ == "__main__":
    main()
