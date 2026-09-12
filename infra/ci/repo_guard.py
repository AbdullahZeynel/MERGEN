"""Block credentials, infrastructure addresses and bulk data from the repository.

AGENTS.md forbids committing real hosts, tokens, keys, weights and datasets.
`.gitignore` does not scan content and does not protect an already tracked
file, so this guard reads the tracked files themselves and fails the build.

Findings never echo the matched value: the report gives the rule, the file and
the line number only, so a leaked secret is not copied into CI logs.

    python infra/ci/repo_guard.py            # tracked files of this checkout
    python infra/ci/repo_guard.py --root DIR
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 1024 * 1024

# Git'te asla bulunmaması gereken dosya adları. `.env.example` ve türevleri
# bilinçli istisnadır; içerikleri ayrıca denetlenir.
SECRET_FILENAMES = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)\.env\.(?!.*\.example$).+$"),
    re.compile(r"(^|/)[^/]*\.env$"),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$"),
    re.compile(r"(^|/)\.(netrc|pypirc|npmrc|htpasswd)$"),
    re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$"),
    re.compile(r"(^|/)credentials[^/]*\.json$"),
    re.compile(r"(^|/)service-account[^/]*\.json$"),
    re.compile(r"\.tfstate(\.[^/]+)?$"),
    re.compile(r"(^|/)settings\.local\.json$"),
    re.compile(r"(^|/)\.git/"),
)

# .gitignore bu desenleri kaybederse koruma sessizce zayıflar.
REQUIRED_IGNORES = (".env", "*.env", "*.pem", "*.key", ".local/",
                    "__pycache__/", "node_modules/", ".venv/")

# Saglayici anahtarlari: bicimleri kendi basina yeterli kanit.
PROVIDER_TOKENS = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-|ant-)?[0-9A-Za-z_-]{32,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[0-9A-Za-z]{30,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("json-web-token", re.compile(r"\beyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\b")),
)

# Örnek env dosyalarında yalnız bu biçimdeki değerler serbest: yerel adres,
# sayı, mantıksal değer, mutlak yol, açık yer tutucu ve örnek alan adı.
ENV_SAFE_VALUE = re.compile(
    r"^(|true|false|yes|no|on|off|\d+|/[\w./-]*|~?/[\w./-]*"
    r"|localhost(:\d+)?|127\.0\.0\.1(:\d+)?|0\.0\.0\.0(:\d+)?"
    r"|https?://(localhost|127\.0\.0\.1)(:\d+)?(/[\w./-]*)?"
    r"|https?://(www\.)?example\.(com|org|net)(/[\w./-]*)?"
    r"|<[^>]*>|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|example\.(com|org|net))$",
    re.IGNORECASE,
)
ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
ENV_EXAMPLE = re.compile(r"(^|/)(\.env|[^/]*\.env|[^/]*\.env\.[^/]+)\.example$|(^|/)\.env\.example$")

# Weight, dataset and archive extensions that must stay out of Git.
BULK_SUFFIXES = (
    ".pt", ".pth", ".safetensors", ".ckpt", ".onnx", ".h5", ".hdf5",
    ".joblib", ".pkl", ".pickle", ".npz", ".npy",
    ".nii", ".nii.gz", ".dcm", ".maf", ".maf.gz", ".vcf", ".vcf.gz",
    ".zip", ".tar", ".tar.gz", ".7z",
)

# Values that clearly mark an empty example rather than a real credential.
PLACEHOLDERS = re.compile(
    r"^(|-|none|null|todo|tbd|changeme|change_me|placeholder|example|examples?\.com"
    r"|x{3,}|\*{3,}|\.{3,}|<[^>]*>|\$\{?[a-z_]+\}?|your[-_a-z]*|dummy|fake|sample)$",
    re.IGNORECASE,
)

# Only a quoted literal counts: `token = os.environ[...]` is code, not a secret.
# The keyword must end the word, so `tokenizer` and `secretariat` do not match.
SECRET_KEY = re.compile(
    r"(?i)\b([a-z0-9_]*(?:token|secret|passwd|password|api[_-]?key|access[_-]?hash"
    r"|private[_-]?key|credential)(?![a-z]))\s*[:=]\s*['\"]([^'\"\n]*)['\"]"
)
PRIVATE_KEY_BLOCK = re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")
SSH_PUBLIC_KEY = re.compile(r"\bssh-(?:rsa|ed25519|dss)\s+AAAA[0-9A-Za-z+/]{20,}")
MAGIC_DNS = re.compile(r"\b[a-z0-9][a-z0-9-]*\.ts\.net\b", re.IGNORECASE)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")

# Loopback, unspecified, RFC1918, link-local, multicast and the RFC5737
# documentation ranges are safe to write down.
DOC_NETWORKS = tuple(ipaddress.ip_network(n) for n in
                     ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"))


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        yer = f"{self.path}:{self.line}" if self.line else self.path
        return f"  {yer}  [{self.rule}] {self.detail}"


def tracked_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                         check=True, capture_output=True, text=True).stdout
    return [root / name for name in out.split("\0") if name]


def _ip_is_public(text: str) -> bool:
    """True only for a host address that is neither private nor documentation."""
    address_text, _, prefix = text.partition("/")
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        return False
    if prefix:                       # a network literal such as 100.64.0.0/10
        return False
    if (address.is_private or address.is_loopback or address.is_multicast
            or address.is_unspecified or address.is_link_local
            or address.is_reserved or str(address) == "255.255.255.255"):
        return False
    return not any(address in network for network in DOC_NETWORKS)


SECRET_WORD = re.compile(
    r"(?i)(?:token|secret|passwd|password|api[_-]?key|access[_-]?hash"
    r"|private[_-]?key|credential)(?![a-z])"
)


def is_env_example(path: str) -> bool:
    return bool(ENV_EXAMPLE.search(path))


def scan_env_example(path: str, text: str) -> list[Finding]:
    """Örnek env dosyası yalnız boş ya da açıkça demo değer taşımalı."""
    bulgular: list[Finding] = []
    anahtar_sayisi = 0
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "repo-guard: allow" in line:
            continue
        eslesme = ENV_ASSIGNMENT.match(line)
        if not eslesme:
            bulgular.append(Finding(path, number, "env-example-format",
                                    "ANAHTAR=deger biçiminde değil"))
            continue
        anahtar_sayisi += 1
        name, value = eslesme.group(1), eslesme.group(2).strip("\"'")
        if SECRET_WORD.search(name) and value:
            bulgular.append(Finding(path, number, "env-example-secret",
                                    f"'{name}' örnek dosyada boş bırakılmalı"))
        elif value and not ENV_SAFE_VALUE.match(value):
            bulgular.append(Finding(path, number, "env-example-value",
                                    f"'{name}' gerçek görünen bir değer taşıyor"))
    if anahtar_sayisi == 0:
        bulgular.append(Finding(path, 0, "env-example-empty",
                                "örnek dosyada hiç anahtar yok"))
    return bulgular


def scan_text(path: str, text: str) -> list[Finding]:
    bulgular: list[Finding] = []
    if is_env_example(path):
        bulgular.extend(scan_env_example(path, text))
    for number, line in enumerate(text.splitlines(), start=1):
        if "repo-guard: allow" in line:
            continue
        for rule, pattern in PROVIDER_TOKENS:
            if pattern.search(line):
                bulgular.append(Finding(path, number, rule, "sağlayıcı anahtarı biçimi"))
        if PRIVATE_KEY_BLOCK.search(line):
            bulgular.append(Finding(path, number, "private-key", "özel anahtar bloğu"))
        if SSH_PUBLIC_KEY.search(line):
            bulgular.append(Finding(path, number, "ssh-key", "gömülü SSH anahtarı"))
        for host in MAGIC_DNS.findall(line):
            bulgular.append(Finding(path, number, "tailscale-host",
                                    f"{len(host)} karakterlik .ts.net adresi"))
        for raw in IPV4.findall(line):
            if _ip_is_public(raw):
                bulgular.append(Finding(path, number, "public-ip",
                                        "genel IPv4 adresi (yer tutucu kullanın)"))
        for name, value in SECRET_KEY.findall(line):
            if len(value) >= 8 and not PLACEHOLDERS.match(value):
                bulgular.append(Finding(path, number, "secret-value",
                                        f"'{name}' dolu bir değer taşıyor"))
    return bulgular


def scan_file(path: Path, root: Path) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    if not path.is_file():
        return []
    boyut = path.stat().st_size
    bulgular: list[Finding] = []
    isim = relative.lower()
    # Örnek dosyalar bilinçli istisna; adları değil içerikleri denetlenir.
    for pattern in ([] if is_env_example(relative) else SECRET_FILENAMES):
        if pattern.search(relative):
            bulgular.append(Finding(relative, 0, "secret-file",
                                    "bu dosya adı Git'te olmamalı"))
            break
    if any(isim.endswith(suffix) for suffix in BULK_SUFFIXES):
        bulgular.append(Finding(relative, 0, "bulk-file",
                                "ağırlık/veri/arşiv uzantısı Git'te olmamalı"))
    if boyut > MAX_BYTES:
        bulgular.append(Finding(relative, 0, "large-file",
                                f"{boyut // 1024} KiB > {MAX_BYTES // 1024} KiB"))
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return bulgular                      # ikili dosya: içerik taranmaz
    return bulgular + scan_text(relative, text)


def scan_gitignore(root: Path) -> list[Finding]:
    """Koruma .gitignore'dan sessizce çıkarılmasın."""
    yol = root / ".gitignore"
    if not yol.is_file():
        return [Finding(".gitignore", 0, "gitignore-missing", ".gitignore yok")]
    satirlar = {s.strip() for s in yol.read_text(encoding="utf-8").splitlines()}
    return [Finding(".gitignore", 0, "gitignore-weakened", f"'{desen}' deseni kayıp")
            for desen in REQUIRED_IGNORES if desen not in satirlar]


def scan_repository(root: Path) -> list[Finding]:
    bulgular = scan_gitignore(root)
    for path in tracked_files(root):
        bulgular.extend(scan_file(path, root))
    return bulgular


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repository guard")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    root = args.root.resolve()
    bulgular = scan_repository(root)
    if not bulgular:
        print("repo-guard: temiz")
        return 0
    print(f"repo-guard: {len(bulgular)} bulgu (değerler yazdırılmaz)")
    for bulgu in bulgular:
        print(bulgu)
    print("\nYanlış pozitifse satır sonuna 'repo-guard: allow' yorumu ekleyin.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
