"""译名审校：按专业词表筛出含技术内容的 EN↔ZH 段。

配合 `audit_pairs.py` 用：先用本脚本把范围缩到真正需要人看的技术段，
再用 `audit_pairs.py <章> --grep '<术语>'` 逐条比对。

两个内置词表：
  --set crypto  密码学 / Web3 / 数学 / 计算机科学（第一轮）
  --set stats   统计 / 随机性 / 机制设计（补第一轮的盲区）

用法：
  python3 pipeline/audit_tech_pairs.py --set crypto            # 打到 stdout
  python3 pipeline/audit_tech_pairs.py --set stats --out /tmp/t2.txt
  python3 pipeline/audit_tech_pairs.py --set crypto 9 22       # 只看第 9、22 章

[坑·留档] 词表必须按 `[\n|]+` 切分，不能按 `\s`。按空白切会把
"proof of work" 拆成 proof/of/work，而 `of` 会匹配 "the house" 里的 of ——
空分支一旦产生，正则就匹配**每一段**，筛选形同虚设（曾因此把 4808 段全捞出来）。
短词元（长度 ≤2）同理，必须为空。
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_pairs import load, strip_html  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 刻意排除 sign / mod / graph / model 这类会误命中普通叙事的词；
# 多词短语必须用 \n 或 | 分隔，保留整体不拆散。
CRYPTO_TERMS = r"""
factoriz|modulo|elliptic|prime number|entropy|negentropy|hash function|hashes
|XOR|nim sum|quadratic|sortition|cryptographic sortition|garbled|garbling|obfuscat
|zero-knowledge|zero knowledge|steganograph|permutation|threshold signature|threshold key
|attestation|unclonable|erasure cod|trie|merkle|signature|signatures|sign the
|symmetric|public key|private key|blind signature|blinded share|nonce|ciphertext|plaintext
|encrypt|decrypt|one-time pad|synerg|sybil|collusion|arbitrage|price of anarchy
|binomial|geometric mean|prefix tree|bounded.depth|gradient descent|adversarial
|convolutional|softmax|perplexity|temperature sampl|language model|neural network
|world model|simulator|simulation|differential privacy|privacy-preserving|consensus
|slippage|insider trading|invariant|timestep|tiling|commit-reveal|commitment scheme
|blockchain|smart contract|DAO|quadratic funding|quadratic voting|reputation score
|key allocation|voting key|social recovery|recovery mode|secret sharing|key split
|proof of work|proof of stake|validator|sybil resistance|anonymity set|metadata
|cover traffic|padding|randomized infrared|formal verification|formal methods
|information-theoretic|Shannon|linear transformation|eigenvect|directed acyclic
|cooperative game|game theor|Nash|zero-sum|positive-sum|negative-sum|burn after reading
|encrypted|publicly verifiable|verifiable|recompute|rollback|virtual machine|bytecode
|clipping|gradient|optimization problem|convex|quadratic equation|exponentiate
|modular arithmet|cipher|one-way function|trapdoor|homomorphic|obtain a signature
"""

STATS_TERMS = r"""
randomiz|bias|unbiased|distribution|variance|deviation|converge|convergence
|correlation|independen|mutually exclusive|probabilistic|deterministic|logarithmic
|exponential|approximat|asymptotic|threshold|entropy|sampling|sample size
|commit|reveal|commitment|sealing|seal|nonce|replay|forward secrecy|entropy pool
|key rotation|rotate|shares|secret shar|interpolat|polynomial|modular
|integer|exponent|prime|gcd|coprime|inverse|one-way|trapdoor|hash rate|difficulty
|block|chain|ledger|consensus|validator|stake|slashing|finality|reorg
|mix node|cover|delay|batching|reorder|padding|anonymous set|linkability|metadata
|side channel|timing|leak|covert channel|watermark|watermarking|steganalysis
|compress|decompress|redundan|parity|checksum|truncat|invert
|preimage|digest|blockchain|smart contract|token|wallet|key pair|private
|certificate|chain of trust|root of trust|verifiable|provable|soundness|completeness
|witness|challenge|prover|verifier|simulation paradigm|semantically secure
"""

SETS = {'crypto': CRYPTO_TERMS, 'stats': STATS_TERMS}


def compile_terms(raw: str) -> re.Pattern[str]:
    terms = [t.strip() for t in re.split(r'[\n|]+', raw) if t.strip()]
    short = [t for t in terms if len(t) <= 2]
    if short:
        # 短词元几乎必然是误命中源，宁可构建失败也不要静默放行
        raise SystemExit(f'词表里出现短词元 {short}：会匹配普通词，请改成多词短语')
    return re.compile('|'.join(terms), re.I)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--set', choices=sorted(SETS), default='crypto',
                    help='选哪套词表（默认 crypto）')
    ap.add_argument('--out', type=Path, help='写到文件；缺省打到 stdout')
    ap.add_argument('chapters', nargs='*', type=int, help='只看这些章，缺省全书')
    args = ap.parse_args()

    rx = compile_terms(SETS[args.set])
    chapters = args.chapters or list(range(1, 33))
    hits: list[tuple[int, str, str, str, str]] = []
    for ch in chapters:
        for sid, en, role, zh in load(ch):
            e = strip_html(en)
            if not e.strip() or not rx.search(e):
                continue
            hits.append((ch, sid, role, e, strip_html(zh)))

    def fmt(rows):
        for ch, sid, role, e, z in rows:
            yield f'── ch{ch:02d} {sid} [{role}]\nEN: {e}\nZH: {z}\n'

    if args.out:
        args.out.write_text(''.join(fmt(hits)), encoding='utf-8')
        print(f'命中 {len(hits)} 段 → {args.out}', file=sys.stderr)
    else:
        sys.stdout.write(''.join(fmt(hits)))
        print(f'命中 {len(hits)} 段', file=sys.stderr)

    counts = collections.Counter(ch for ch, *_ in hits)
    print(' '.join(f'ch{k:02d}:{v}' for k, v in sorted(counts.items())), file=sys.stderr)


if __name__ == '__main__':
    main()
