#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""隐私闸门：扫描**将要提交进仓库的内容**，阻止内部网关信息 / 凭据再次进仓库。

扫描对象是两份，任一命中即失败（f4c2c65 只读工作区，漏掉已 `git add` 的内容，见 P1-12）：

  A. **git 索引里的 blob**（`git ls-files -s` 取 stage 0 的 oid，`git cat-file --batch` 读字节）
     ——下一次提交真正会写进历史的字节；未合并路径的各 stage 也一并扫；
  B. 同一批路径在**工作区**的当前字节（符号链接不跟随，避免读到仓库外的本机文件）。

规则（刻意不写具体 provider 名，避免闸门自身成为泄漏源）：

  1. 凭据字面量——对**每个受跟踪文本文件的每一行**生效（不再只覆盖 pipeline/*.py）：
     `sk-` 形状、AWS Access Key ID / Secret Access Key、Google API Key、Stripe 密钥、
     GitHub / Slack 令牌、JWT、`-----BEGIN … PRIVATE KEY-----`、Authorization 头，
     以及「把 16 位以上字面量赋给 api_key / token / secret / password 一类键」。
  2. URL 端点——一行里的**每一个** http(s) URL 都单独判定（不只第一个），命中任一条即算：
     a. 主机像内网 / 临时隧道 / 随机生成：私有后缀、内网标签、gw 类标签、隧道域名、
        十六进制随机标签、私网 / 保留地址直连（公网 IP 放过）、非标准端口上的 API 形状
        路径——**任何文件**都判；
     b. 路径是「调用型」端点（chat/completions、embeddings、messages、generateContent、
        images/generations、rpc/invoke/execute…）——散文里也判，只放过下面「刻意放过的」
        那种公开 API 引用形状；代码 / 配置文件里由 2d 兜住；
     c. 被绑给配置键或交给网络调用（`base_url = "http…"`、`fetch("http…")`、
        `urlopen("http…")`）且主机不在公开白名单——**任何文件**都判；
        散文里的 `端点：https://…` 这种「冒号 + 空格」写法不算绑定，否则
        文档里引用一个公开 API 的说明会被当成硬编码端点（见文件头「刻意放过的」）；
        JSON/YAML 里的 `"endpoint": "http…"` 归 d（配置文件按代码口径判）。
     d. 代码 / 配置文件（.py/.js/.css/.json/.yml/.toml/.sh…）里出现非白名单主机
        ——沿用 f4c2c65 的口径；
     e. 代码 / 配置文件里出现版本化路径（`/v1/…`）——即便主机在白名单上也算硬编码端点，
        「模型调用端点只允许经环境变量注入」这条不因主机公开而破例（散文里的版本化路径
        不判，见「刻意放过的」）。
  3. provider 命名——分两层：
     a. **内置形状规则**（入库，任何 clone 都生效，不含任何具体 provider 名）：
        网关 / 边缘防护把自家支持文档 URL、错误码回显进 error 字段的形态；
     b. 本机 `.privacy-terms`（不入库，一行一个子串，`#` 起头为注释）里的自定义词条。
        该文件按设计不入库，缺席时只是少了一层本机词条（基础层仍生效），
        脚本会往 stderr 提示；`--require-terms` 可让缺席直接 exit 2，供本机自查。

刻意放过的（避免误报淹没真泄漏，见 P1-11 的假阳性）：

  * 散文 / 文档（.md/.html/.svg/.log/.jsonl…）里对公开 API 的**元数据引用**，
    例如列出模型清单的 `/v1/models` 这类只读路径。它不带凭据、不在配置绑定上下文里、
    主机也不像内网服务时按文档处理；同一行若出现凭据或配置绑定，规则 1 / 2c 照样拦。
  * 调用型路径若挂在「公开 API 引用形状」的主机上（`api.<单个英文词>.<字母后缀>` 三段、
    无端口，见 `PUBLIC_API_REFERENCE_RE`）——公开域名的自建部署无法与厂商文档按形状区分，
    这里取「宁可放过文档引用」的一边；四段主机（`api.<词>.<内部域>`）、多词 / 带连字符的
    主机、以及任何非公开主机名仍然判。
  * 主机在 `PUBLIC_HOST_ALLOW` 里的引用（站点、许可证、上游原文等）；本机地址
    （localhost / 127.0.0.1）本身也不算泄漏，只有配上 API 形状路径才判；公网 IP
    （裸写 1.1.1.1 这类公共 DNS）不算私网直连。
    （注意：本文件自身也在扫描范围内，注释里不要写任何非白名单主机名。）
  代价（不假装覆盖）：本机自建网关若挂在一个干净的 `api.<词>.com` 形状的公开域名上、
  只出现在散文里、又不带凭据与配置绑定，这一版仍放过。

用法: python3 pipeline/check_privacy.py
      python3 pipeline/check_privacy.py --require-terms   # CI 用：词表缺席即 exit 2
      # 有命中则打印「文件:行号: 来源: 原因」并退出 1
退出码: 0 通过 / 1 有命中 / 2 读不到 git 索引内容，或 --require-terms 下词表缺席（fail-closed）
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_TERMS = ROOT / ".privacy-terms"

# [P0] 规则 3 的**基础层**：入库、任何 clone 都生效。
# 原来这一层完全依赖不入库的 .privacy-terms，于是 CI 与其他贡献者处恒为空 ——
# 唯一能抓「provider 命名」的一层只在作者本机跑过，而脚本照样打印「通过」。
# 这里按**形状**（不是具体名字，避免闸门自身成为泄漏源）覆盖外部错误体的典型形态：
# 网关/边缘防护的服务端错误会把自家支持文档 URL 与错误码回显进 error 字段。
BUILTIN_TERM_PATTERNS = (
    # 边缘防护 / API 网关的支持文档 URL（错误体回显的形态）
    re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|dev|io)/support/troubleshooting\b"),
    # 「HTTP <码>: {json…」后面跟着的支持文档链接
    re.compile(r'"(?:type|url|documentation)"\s*:\s*"https?://[^"]+/support/'),
    # 错误体里常见的厂商错误码字段
    re.compile(r'"(?:error_?code|error_?type)"\s*:\s*"\d{6,}"'),
)

MAX_BYTES = 8 * 1024 * 1024          # 单份内容上限，超过按不可扫处理
SKIP_MODES = {"160000"}              # 160000 = 子模块 gitlink（内容不在本仓库索引里）
CODE_SUFFIX = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".json", ".css", ".scss",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".env", ".ps1", ".bat",
}

# ---------------------------------------------------------------- 规则 1：凭据
# 只收「形状明确」的形状；宽松的带引号赋值会误伤 normalize_zh.py:119 的正则
# （`TOKEN = "[0-9A-Za-z]…"`），见 docs/lessons.md §8「验收标准本身要先被验收」。
_ASSIGN_KEY = (
    r"api[_-]?key|api[_-]?secret|secret[_-]?key|client[_-]?secret|"
    r"access[_-]?key(?:[_-]?id)?|auth[_-]?token|access[_-]?token|"
    r"secret|token|password|passwd|credential"
)
SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("疑似 sk- 形状的密钥字面量", re.compile(r"sk-[A-Za-z0-9_-]{16,}")),
    ("疑似 AWS Access Key ID",
     re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    ("疑似 AWS Secret Access Key",
     re.compile(r"(?i)aws_?secret_?(?:access_?)?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}")),
    # 真实 Google API key 固定 39 字符，但写死 `{35}\b` 会在长度差一位时整个漏掉
    # （实测 AIza + 36 个字符不再匹配）。这里取 30..50 的区间，与其它凭据规则一致。
    ("疑似 Google API Key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,50}\b")),
    ("疑似 Google OAuth 凭据", re.compile(r"\by29\.[0-9A-Za-z_-]{20,}")),
    ("疑似 Stripe 密钥",
     re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{10,}|\bwhsec_[0-9A-Za-z]{16,}")),
    ("疑似 GitHub 令牌",
     re.compile(r"\bgh[pousr]_[0-9A-Za-z]{20,}|\bgithub_pat_[0-9A-Za-z_]{20,}")),
    ("疑似 Slack 令牌", re.compile(r"\bxox[abposr]-[0-9A-Za-z-]{10,}")),
    ("疑似 JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}")),
    ("疑似私钥内容", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("疑似 Authorization 头凭据",
     re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{24,}")),
    ("疑似硬编码的凭据赋值",
     re.compile(rf"(?i)\b(?:{_ASSIGN_KEY})\b\s*[:=]\s*[\"']?[A-Za-z0-9/+_.\-]{{16,}}")),
]

# ---------------------------------------------------------------- 规则 2：端点
URL_RE = re.compile(
    r"https?://(?:\[[0-9A-Fa-f:.]+\][^\s\"'()<>\[\]{},;`]*"   # IPv6 字面量主机
    r"|[^\s\"'()<>\[\]{},;`]+)")
URL_HEAD_RE = re.compile(r"^https?://(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._-]+)(?::(\d+))?")
# 调用型端点：真正发请求的路径（/v1/models 这类只读清单不算，见文件头「刻意放过的」）
INVOKE_PATH_RE = re.compile(
    r"(?i)chat/completions|/completions\b|/embeddings\b|/messages\b|/responses\b|"
    r"generatecontent|images/generations|audio/(?:speech|transcriptions)|"
    r"/rpc\b|/invoke\b|/execute\b|openai/deployments")
VERSION_PATH_RE = re.compile(r"/v\d+[a-z0-9]*(?:/|$)", re.I)
# 绑定到配置键 / 交给网络调用的上下文；只认代码式 `=` 与调用式 `(`，
# 不认散文里的「端点：https://…」（中文冒号写法与 YAML 冲突，见文件头 2c）
URL_BINDING_RE = re.compile(
    r"(?i)[\"']?[A-Za-z0-9_.-]*(?:url|uri|endpoint|host|addr|address|origin|base)"
    r"[\"']?\s*=\s*[\"']?https?://"
    r"|(?:fetch|urlopen|urlretrieve|requests\.(?:get|post|put|patch|delete))"
    r"\s*\(\s*[\"']?https?://")
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
HEX_LABEL_RE = re.compile(r"^[0-9a-f]{12,}$")
# 散文里「厂商公开 API 文档」的形状：api.<单个英文词>.<字母后缀>，无端口。
# 刻意不写具体 provider 名（见文件头），因此用形状近似：
# 这样的主机若只被引用调用型路径，放行；api.<词>.<内部域>（四段 / 多词）仍判。
PUBLIC_API_REFERENCE_RE = re.compile(
    r"^(?:api|apis|www|docs|developer|developers)\.[a-z]{2,12}\.[a-z]{2,}$")
PRIVATE_SUFFIXES = (".internal", ".corp", ".lan", ".intranet", ".private", ".home.arpa",
                     ".localdomain", ".invalid", ".test")
INTERNAL_LABELS = {"internal", "corp", "intranet", "lan", "private", "vpc", "mesh",
                   "cluster", "kube", "k8s", "gw", "gateway", "relay", "proxy", "tunnel"}
TUNNEL_HOSTS = ("ngrok", "trycloudflare", "duckdns", "ddns.net", "no-ip", "hopto",
                "serveo", "loca.lt", "localtunnel", "localhost.run", "bore.pub",
                "cfargotunnel", "cloudflared")
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

# 代码里只允许这些公开主机（文档里的调研链接按规则 2a/2b/2c 判，不在此列）
PUBLIC_HOST_ALLOW = {
    "github.com", "0xvanfer.github.io", "snowmoon.vanfer.tech", "vitalik.eth.limo",
    "www.w3.org", "w3.org", "raw.githubusercontent.com", "localhost", "127.0.0.1",
}

MAX_PRINTED_HITS = 200


class GitError(RuntimeError):
    """读不到索引内容：不能当成「干净」放行。"""


# ---------------------------------------------------------------- 内容来源
def _git(*args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitError(f"`git {' '.join(args)}` 失败：{err[-1] if err else '未知错误'}")
    return proc.stdout


def index_entries() -> tuple[list[tuple[str, str, str]], int]:
    """返回 [(相对路径, mode, oid)] 与未合并（stage != 0）路径数。"""
    out = _git("ls-files", "-s", "-z")
    entries: list[tuple[str, str, str]] = []
    unmerged = 0
    for rec in out.split(b"\0"):
        if not rec:
            continue
        meta, _, raw = rec.partition(b"\t")
        parts = meta.split()
        if len(parts) < 3 or not raw:
            continue
        mode, oid, stage = (p.decode("ascii", "replace") for p in parts[:3])
        if mode in SKIP_MODES:                 # 子模块：内容不在本仓库索引里
            continue
        if stage != "0":
            unmerged += 1
        entries.append((raw.decode("utf-8", "surrogateescape"), mode, oid))
    return entries, unmerged


def read_blobs(oids: list[str]) -> dict[str, bytes]:
    """一次 `git cat-file --batch` 读全部索引 blob；缺对象直接报，不静默跳过。"""
    if not oids:
        return {}
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT,
                          input=("\n".join(oids) + "\n").encode(), capture_output=True)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise GitError(f"git cat-file --batch 失败：{err[-1] if err else '未知错误'}")
    data, pos, out = proc.stdout, 0, {}
    for oid in oids:
        nl = data.find(b"\n", pos)
        if nl < 0:
            raise GitError(f"git cat-file 输出不完整（停在 {oid}）")
        head = data[pos:nl].decode("utf-8", "replace").split()
        pos = nl + 1
        if len(head) < 3 or head[1] == "missing":
            raise GitError(f"索引引用的对象读不到：{oid}（仓库可能不完整）")
        try:
            size = int(head[2])
        except ValueError:
            raise GitError(f"无法解析对象 {oid} 的大小：{head[2]!r}") from None
        if pos + size > len(data):
            raise GitError(f"git cat-file 输出被截断（{oid}）")
        out[oid] = data[pos:pos + size]
        pos += size + 1
    return out


def worktree_bytes(rel: str) -> bytes | None:
    """工作区版本；符号链接不跟随（否则会读到仓库外的本机文件）。"""
    path = ROOT / rel
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_bytes()
    except OSError:
        return None


def as_text(data: bytes) -> str | None:
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ---------------------------------------------------------------- 判定
def is_private_ip(host: str) -> bool:
    """私网 / 环回 / 链路本地 / 保留地址（公网 IP 如 1.1.1.1 不算，避免误报）。"""
    raw = host[1:-1] if host.startswith("[") else host
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_unspecified)


def suspicious_host(host: str, port: str | None, api_shaped: bool) -> str | None:
    low = host.lower().rstrip(".")
    if not low or low in LOOPBACK_HOSTS:
        return None      # 本机地址本身不是泄漏；API 形状路径由 2b / 2e 去判
    if any(low.endswith(sfx) for sfx in PRIVATE_SUFFIXES):
        return f"疑似内网域名（{low}）"
    if any(t in low for t in TUNNEL_HOSTS):
        return f"疑似临时隧道域名（{low}）"
    if IPV4_RE.match(low) or low.startswith("["):
        if is_private_ip(low):
            return f"私网地址直连（{low}）"
    for label in low.split("."):
        if label in INTERNAL_LABELS:
            return f"主机名含内网 / 网关标签（{label}）"
        if len(label) > 2 and label.startswith("gw") and label[2:].isdigit():
            return f"主机名含网关标签（{label}）"
        if label.endswith("-gw"):
            return f"主机名含网关标签（{label}）"
        if HEX_LABEL_RE.match(label):
            return f"主机名疑似随机生成（{label}）"
    if port and port not in ("80", "443") and api_shaped and low not in LOOPBACK_HOSTS:
        return f"非标准端口上的 API 端点（{low}:{port}）"
    return None


def why_for_line(line: str, is_code: bool) -> str | None:
    for reason, rx in SECRET_RULES:
        if rx.search(line):
            return reason
    bound = bool(URL_BINDING_RE.search(line))
    for m in URL_RE.finditer(line):              # 一行里的每个 URL 都单独判
        head = URL_HEAD_RE.match(m.group(0))
        if not head:
            continue
        host, port = head.group(1), head.group(2)
        low = host.lower()
        tail = m.group(0)[head.end():]
        invoke = bool(INVOKE_PATH_RE.search(tail))
        version = bool(VERSION_PATH_RE.search(tail))
        why = suspicious_host(host, port, invoke or version)
        if why:
            return why
        if invoke:
            # 散文里只放过「公开 API 引用形状」的主机（见文件头 2b / 刻意放过的）
            if is_code or not PUBLIC_API_REFERENCE_RE.match(low):
                return f"硬编码的调用型端点（{host}）"
        if is_code and version:
            return f"代码里硬编码的版本化端点（{host}）"  # 2e：白名单主机也不放过
        if is_code and low not in PUBLIC_HOST_ALLOW:
            return f"代码里的非白名单主机 {host}"       # 2d
        if bound and low not in PUBLIC_HOST_ALLOW:
            return f"配置里绑定的非白名单主机 {host}"    # 2c
    return None


def local_terms() -> list[str]:
    if not LOCAL_TERMS.exists():
        return []
    terms = []
    for line in LOCAL_TERMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    return terms


def builtin_term_hit(line: str) -> str | None:
    """内置词表层：按形状匹配，不含任何具体 provider 名。"""
    for pattern in BUILTIN_TERM_PATTERNS:
        if pattern.search(line):
            return f"命中内置形状规则 {pattern.pattern!r}"
    return None


def show(path: str) -> str:
    return path.encode("utf-8", "replace").decode("utf-8")


def main() -> int:
    # [P0] 规则 3 的基础层已改为**内置形状规则**（BUILTIN_TERM_PATTERNS），入库、
    # 任何 clone 都生效；.privacy-terms 降级为本机追加词条。--require-terms 用于
    # 自查「本机词表是否还在」，CI 不必带（基础层已经恒定生效）。
    require_terms = "--require-terms" in sys.argv[1:]
    try:
        entries, unmerged = index_entries()
        blobs = read_blobs([oid for _, _, oid in entries])
    except GitError as exc:
        print(f"隐私闸门未通过：读不到 git 索引内容，无法确认将要提交的内容（{exc}）",
              file=sys.stderr)
        return 2

    terms = local_terms()
    hits: dict[tuple[str, int, str], set[str]] = {}
    scanned = skipped = 0
    seen_paths: set[str] = set()

    for rel, _mode, oid in entries:
        is_code = Path(rel).suffix.lower() in CODE_SUFFIX
        seen_paths.add(rel)
        for label, data in (("索引", blobs.get(oid)), ("工作区", worktree_bytes(rel))):
            if data is None or len(data) > MAX_BYTES:
                skipped += 1
                continue
            text = as_text(data)
            if text is None:
                skipped += 1
                continue
            scanned += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                why = why_for_line(line, is_code)
                if why is None:
                    # 规则 3：内置形状层先跑（任何 clone 都生效），本机词表再补
                    why = builtin_term_hit(line)
                if why is None:
                    why = next((f"命中 .privacy-terms 词条「{t}」" for t in terms if t in line),
                               None)
                if why:
                    hits.setdefault((rel, lineno, why), set()).add(label)

    if hits:
        print("隐私闸门未通过：以下位置疑似泄漏端点 / 凭据 / provider 信息"
              f"（{len(hits)} 处；来源 = 索引 / 工作区）", file=sys.stderr)
        for (rel, lineno, why), srcs in sorted(hits.items())[:MAX_PRINTED_HITS]:
            label = "+".join(s for s in ("索引", "工作区") if s in srcs)
            print(f"  {show(rel)}:{lineno}: [{label}] {why}", file=sys.stderr)
        if len(hits) > MAX_PRINTED_HITS:
            print(f"  …另有 {len(hits) - MAX_PRINTED_HITS} 处未列出", file=sys.stderr)
        return 1

    note = f"，含 {unmerged} 个未合并路径的全部 stage" if unmerged else ""
    # [P0] 规则 3 的基础层已内置入库，任何 clone 都会跑；.privacy-terms 只是本机追加。
    # --require-terms 保留给「本机确实该有词表却丢了」的自查：它要求本机词表存在。
    if not terms:
        msg = (f"本机未找到 {LOCAL_TERMS.name}：规则 3 的**基础层仍已生效**"
               f"（内置形状规则 {len(BUILTIN_TERM_PATTERNS)} 条），"
               f"缺的是本机自定义词条")
        if require_terms:
            print(f"隐私闸门未通过：{msg}。请提供该文件，或去掉 --require-terms。",
                  file=sys.stderr)
            return 2
        print(f"提示：{msg}。", file=sys.stderr)
    print(f"隐私闸门通过：{len(seen_paths)} 个受跟踪路径{note}，"
          f"索引内容与工作区内容共逐行扫描 {scanned} 份文本，"
          f"跳过 {skipped} 份（二进制 / 超 {MAX_BYTES // 1048576} MiB / 工作区缺失）；"
          f"规则 = 凭据字面量、端点与主机形状、代码非白名单主机、"
          f"provider 命名内置形状 {len(BUILTIN_TERM_PATTERNS)} 条"
          + (f"、.privacy-terms 词条 {len(terms)} 条" if terms else "（本机词表缺席）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
