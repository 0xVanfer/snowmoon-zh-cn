"""EN↔ZH 逐段对齐：按 segment id 配对英文原文与中文译文。

用途：审校专业领域（密码学 / Web3 / 数学 / CS）译名是否准确。
先跑 `pipeline/audit_tech_pairs.py` 把范围缩到技术段，再用本脚本逐条比对。

用法：
    python3 pipeline/audit_pairs.py 9 12                    # 只看第 9、12 章
    python3 pipeline/audit_pairs.py --grep 'garbled|trie'   # 只看含关键词的段
    python3 pipeline/audit_pairs.py 9 > /tmp/ch9.txt        # 导出该章全文对照
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(ch):
    en = json.load(open(os.path.join(ROOT, f'sources/work/segments/chapter-{ch:02d}.src.json'), encoding='utf-8'))
    zh = json.load(open(os.path.join(ROOT, f'translations/zh/chapter-{ch:02d}.zh.json'), encoding='utf-8'))
    e = {s['id']: s for s in en['segments']}
    z = {s['id']: s for s in zh['segments']}
    out = []
    for sid in sorted(set(e) | set(z)):
        out.append((sid,
                    e.get(sid, {}).get('text', ''),
                    e.get(sid, {}).get('role', ''),
                    z.get(sid, {}).get('text', '')))
    return out


def strip_html(t):
    t = re.sub(r'<c[^>]*>', '', t)
    t = re.sub(r'</c>', '', t)
    t = re.sub(r'<[^>]+>', '', t)
    return t.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--grep', help='只显示 EN 或 ZH 命中该正则的段')
    ap.add_argument('chapters', nargs='*', type=int, help='章号，缺省全书 1-32')
    args = ap.parse_args()
    grep = re.compile(args.grep, re.I) if args.grep else None
    chs = args.chapters or list(range(1, 33))

    for ch in chs:
        for sid, en, role, zh in load(ch):
            e, z = strip_html(en), strip_html(zh)
            if not e.strip():
                continue
            if grep and not (grep.search(e) or grep.search(z)):
                continue
            print(f'── ch{ch:02d} {sid} [{role}]')
            print(f'EN: {e}')
            print(f'ZH: {z}')
            print()


if __name__ == '__main__':
    main()
