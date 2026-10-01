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

不变量：**先校验后落盘**。未通过等价性校验的图不会写进 book/images（旧文件保持不动），
只在 manifest 里记为 invalid。
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

PLACEHOLDER_RE = re.compile(r"\{\{S:([^}]+)\}\}")


def load_glossary() -> dict:
    return json.loads(GLOSSARY.read_text(encoding="utf-8"))


def chapter_of(name: str) -> int:
    m = re.search(r"chapter-(\d+)-fig", name)
    if not m:
        raise SystemExit(f"sources/work/figures 下有无法识别的文件名：{name}"
                         f"（期望 chapter-NN-fig-MM.svg）")
    return int(m.group(1))


def block_seg_ids(blk: dict) -> list[str]:
    """从块的 segs 里取出真正的片段 id（存的是 {{S:id}} 占位符，不是裸 id）。"""
    return PLACEHOLDER_RE.findall("".join(blk.get("segs", []) or []))


def extract_svg(text: str) -> str | None:
    """取模型输出里**最后一个自身标签配平**的 <svg>…</svg>。

    不能用贪婪的 `<svg\\b.*</svg>`：模型若同时给出示例与正稿，会把两段拼成一个非法文件。
    """
    best = None
    for m in re.finditer(r"<svg\b", text):
        seg = text[m.start():]
        depth = 0
        for t in re.finditer(r"<svg\b[^>]*>|</svg\s*>", seg):
            tok = t.group(0)
            if tok.startswith("</"):
                depth -= 1
                if depth == 0:
                    best = seg[:t.end()]
                    break
            elif tok.endswith("/>"):
                if depth == 0:
                    best = tok
                    break
            else:
                depth += 1
    return best


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
        # 上下文：图前最近两条正文的原文/译文
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
            prev_ids = [s for s in block_seg_ids(blk) if s in src_segs]
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
    if not results.exists():
        raise SystemExit(f"结果文件不存在：{results}")
    BOOK_IMG.mkdir(parents=True, exist_ok=True)
    manifest = {}
    if (FIG_DIR / "manifest.json").exists():
        manifest = json.loads((FIG_DIR / "manifest.json").read_text(encoding="utf-8"))

    def degrade(name: str, status: str, **extra) -> None:
        """失败时**只降级状态，保留旧条目的 caption/chars/last_error**。

        [P0] 原实现整条覆盖 manifest[name]，`caption` 键直接消失。
        再跑一次 build_site，缺失的 caption 会被兜底成「插图 chapter-04-fig-01」——
        「想修图」这个操作先毁掉了它唯一的人类可读信息，而且全程绿灯。

        两条必须守住的规则：
          1. `extra` 里传来的空值**不许**覆盖旧值。invalid 分支解析出的 caption
             可能就是空的（模型没输出 CAPTION 行），那正是最需要保住旧值的场合。
          2. `published` 描述的是「这张图当前是否在 book/images 里并且会被发布」，
             不是「本轮调用成功」。降级时旧文件仍然在盘上、仍然会被部署，
             写 published=False 是一条与事实相反的记录。
        """
        old = manifest.get(name) or {}
        entry = {k: v for k, v in old.items()
                 if k not in ("status", "error", "errors", "last_error")}
        for k, v in extra.items():
            if v in (None, "", [], {}) and old.get(k) not in (None, "", [], {}):
                continue          # 新值是空的，保留旧值
            entry[k] = v
        entry["status"] = status
        # 本轮未产出合格图，但旧图仍在盘上、仍会被发布 —— 如实记录，不写反。
        entry["published"] = (BOOK_IMG / f"{name}.svg").exists()
        manifest[name] = entry

    ok = fail = 0
    seen: set[str] = set()
    for lineno, line in enumerate(results.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            # 单行损坏（多半是进程被杀留下的半行）不该让整批结果作废
            print(f"跳过无法解析的结果行 {lineno}: {e}")
            continue
        name = rec.get("id", "")
        if not name:
            print(f"跳过缺少 id 的结果行 {lineno}")
            continue
        seen.add(name)
        src_svg = FIG_DIR / f"{name}.svg"
        if not rec.get("ok"):
            fail += 1
            degrade(name, "error", last_error=str(rec.get("error", ""))[:300])
            print(f"FAIL {name}: {str(rec.get('error', ''))[:120]}")
            continue
        text = rec.get("text") or ""
        m = re.search(r"(?:CAPTION|图注)\s*[:：]\s*(.+)", text)
        caption = re.sub(r"[*`]", "", m.group(1)).strip() if m else ""
        svg = extract_svg(text)
        if not svg:
            fail += 1
            degrade(name, "error", last_error="输出中没有标签配平的 <svg>")
            print(f"FAIL {name}: 无完整 SVG")
            continue
        if not src_svg.exists():
            fail += 1
            degrade(name, "error", last_error=f"缺少原图 {src_svg.name}")
            print(f"FAIL {name}: 缺少原图")
            continue
        # 先写到临时文件校验，通过了才替换正式产物
        tmp = BOOK_IMG / f".{name}.svg.tmp"
        tmp.write_text(svg.strip() + "\n", encoding="utf-8")
        errs = validate(src_svg, tmp)
        if errs:
            tmp.unlink()
            fail += 1
            degrade(name, "invalid", caption=caption, errors=errs[:8], chars=len(svg))
            print(f"INVALID {name}: {errs[0][:140]}")
            continue
        tmp.replace(BOOK_IMG / f"{name}.svg")
        ok += 1
        old = manifest.get(name) or {}
        manifest[name] = {"status": "ok", "caption": caption, "errors": [],
                          "chars": len(svg), "published": True,
                          # 发布来源指纹：让人工发布与模型产物在 schema 上可区分
                          "source": old.get("source", "model")}
        print(f"OK {name}  caption={caption}")

    jobs_file = JOB_DIR / "figures.jsonl"
    if jobs_file.exists():
        want = set()
        for line in jobs_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    want.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError):
                    continue
        gap = sorted(want - seen)
        if gap:
            # [P0] 此前只打印警告、不计入 fail、不影响退出码：out.jsonl 被截断（进程被杀、
            # 断点续跑中断）时，缺失的那几张会以**旧内容**静默发布，alt/图注还是上一轮的。
            # 「这一批没跑完」必须有机器可读的信号。
            fail += len(gap)
            print(f"警告：结果文件缺少 {len(gap)} 个任务的结果：{gap[:6]}", file=sys.stderr)
    # [P0] manifest 原本在整个循环结束后才写一次：中途被 kill 会出现「新图已在盘上、
    # manifest 还是上一轮的 caption/chars/status」这种撕裂状态。先写临时文件再原子替换。
    _manifest_tmp = FIG_DIR / "manifest.json.tmp"
    _manifest_tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    _manifest_tmp.replace(FIG_DIR / "manifest.json")
    print(f"生成 {ok} 张合格中文插图，{fail} 张待修")
    # [P1] apply 永远退出 0：同一个三步流程里调用器（vision_api）会失败、落盘器不会，
    # 于是「这一批没跑完」这件事没有任何机器可读的信号。
    if fail:
        raise SystemExit(f"{fail} 张插图未通过校验或调用失败，manifest 已记为 invalid/error；"
                         f"旧图保持不动。修好后重跑 apply。")


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
