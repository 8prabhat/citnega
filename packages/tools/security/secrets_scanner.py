"""
SecretsScannerTool — scan files and git history for leaked secrets.

Detects:
  - AWS, GCP, Azure, GitHub, Slack, Stripe, Twilio, SendGrid credentials
  - Generic high-entropy strings (base64, hex) in assignment context
  - Private key blocks (RSA, EC, PGP)
  - Connection strings with embedded passwords
  - .env files with real values
  - git history scanning (recent N commits)

Unlike VulnScanner (which looks for code patterns), this tool is specifically
tuned for credential leakage with entropy analysis.
"""

from __future__ import annotations

import base64
import math
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class SecretsScannerInput(BaseModel):
    path: str = Field(description="File or directory to scan")
    scan_git_history: bool = Field(default=False, description="Scan recent git commits for secrets (slow)")
    git_depth: int = Field(default=20, description="Number of recent commits to inspect")
    extensions: list[str] = Field(
        default=[".py", ".js", ".ts", ".go", ".java", ".rb", ".php", ".sh", ".env",
                 ".yaml", ".yml", ".toml", ".json", ".conf", ".config", ".ini", ".xml"],
    )
    entropy_threshold: float = Field(default=4.2, description="Shannon entropy threshold for string flagging")
    exclude_dirs: list[str] = Field(default=[".git", "node_modules", "__pycache__", ".venv", "vendor"])
    max_files: int = Field(default=1000)


class SecretFinding(BaseModel):
    file: str
    line: int
    secret_type: str
    severity: Literal["critical", "high", "medium", "low"]
    snippet: str       # redacted or partial
    entropy: float
    in_git_history: bool
    commit_hash: str


class SecretsScannerOutput(BaseModel):
    scanned_files: int
    git_commits_scanned: int
    findings: list[SecretFinding]
    critical: int
    high: int
    unique_secret_types: list[str]


_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_HEX_CHARS = "0123456789abcdefABCDEF"


def _shannon_entropy(s: str, charset: str) -> float:
    if not s:
        return 0.0
    filtered = [c for c in s if c in charset]
    if len(filtered) < 8:
        return 0.0
    freq: dict[str, int] = {}
    for c in filtered:
        freq[c] = freq.get(c, 0) + 1
    total = len(filtered)
    return -sum((cnt / total) * math.log2(cnt / total) for cnt in freq.values())


def _redact(s: str) -> str:
    if len(s) <= 8:
        return "***"
    return s[:4] + "***" + s[-4:]


class _SecretRule:
    __slots__ = ("name", "pattern", "severity", "group")

    def __init__(self, name: str, pattern: str, severity: str, group: int = 0):
        self.name = name
        self.pattern = re.compile(pattern)
        self.severity = severity
        self.group = group  # capture group index for the secret value


_SECRET_RULES: list[_SecretRule] = [
    _SecretRule("AWS Access Key ID",        r"(AKIA|ASIA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}",     "critical", 0),
    _SecretRule("AWS Secret Access Key",    r"(?i)aws.{0,20}secret.{0,20}['\"]([A-Za-z0-9/+]{40})['\"]", "critical", 1),
    _SecretRule("GitHub Token",             r"(gh[pousr]_[A-Za-z0-9]{36}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})", "critical", 0),
    _SecretRule("Google API Key",           r"AIza[0-9A-Za-z_-]{35}",                            "critical", 0),
    _SecretRule("GCP Service Account JSON", r'"private_key"\s*:\s*"-----BEGIN',                   "critical", 0),
    _SecretRule("Azure SAS Token",          r"(?i)sig=[A-Za-z0-9%+/]{43,}",                      "high", 0),
    _SecretRule("Slack Bot Token",          r"xoxb-[0-9]{11,13}-[0-9]{11,13}-[A-Za-z0-9]{24}",   "critical", 0),
    _SecretRule("Slack Webhook",            r"https://hooks\.slack\.com/services/T[A-Z0-9]{8}/B[A-Z0-9]{8}/[A-Za-z0-9]{24}", "high", 0),
    _SecretRule("Stripe Secret Key",        r"sk_live_[0-9a-zA-Z]{24,}",                         "critical", 0),
    _SecretRule("Stripe Publishable Key",   r"pk_live_[0-9a-zA-Z]{24,}",                         "medium", 0),
    _SecretRule("Twilio Account SID",       r"AC[a-fA-F0-9]{32}",                                "high", 0),
    _SecretRule("Twilio Auth Token",        r"(?i)twilio.{0,20}['\"]([a-f0-9]{32})['\"]",        "critical", 1),
    _SecretRule("SendGrid API Key",         r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}",        "critical", 0),
    _SecretRule("JWT Token",                r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", "high", 0),
    _SecretRule("PEM Private Key",          r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "critical", 0),
    _SecretRule("PGP Private Key",          r"-----BEGIN PGP PRIVATE KEY BLOCK-----",             "critical", 0),
    _SecretRule("SSH DSA Private Key",      r"-----BEGIN DSA PRIVATE KEY-----",                   "critical", 0),
    _SecretRule("Connection String",        r"(?i)(password|pwd)=[^&;\s]{6,}",                    "critical", 0),
    _SecretRule("Postgres URL",             r"postgres(?:ql)?://[^:]+:[^@]{6,}@",                "critical", 0),
    _SecretRule("MySQL URL",                r"mysql://[^:]+:[^@]{6,}@",                           "critical", 0),
    _SecretRule("MongoDB URL",              r"mongodb(?:\+srv)?://[^:]+:[^@]{6,}@",               "critical", 0),
    _SecretRule("Hardcoded Password",       r'(?i)password\s*[=:]\s*["\'](?!your_|<|{|\*)[^"\'\s]{8,}["\']', "high", 0),
    _SecretRule("Bearer Token",             r'[Aa]uthorization[:\s]+[Bb]earer\s+([A-Za-z0-9_.-]{20,})', "high", 1),
    _SecretRule("Basic Auth in URL",        r"https?://[^:@/]+:[^@/]{6,}@",                       "critical", 0),
    _SecretRule("Mailgun API Key",          r"key-[0-9a-zA-Z]{32}",                               "critical", 0),
    _SecretRule("NPM Token",                r"npm_[A-Za-z0-9]{36}",                               "critical", 0),
    _SecretRule("PyPI API Token",           r"pypi-[A-Za-z0-9_-]{128,}",                         "critical", 0),
    _SecretRule("Docker Hub Token",         r"(?i)docker.{0,20}['\"]([A-Za-z0-9_-]{60,})['\"]",  "high", 1),
]

_ENTROPY_PATTERNS = [
    re.compile(r'["\']([A-Za-z0-9+/]{40,}={0,2})["\']'),   # base64-like
    re.compile(r'["\']([0-9a-fA-F]{40,})["\']'),            # hex-like
]


def _scan_text(text: str, filepath: str, entropy_threshold: float, in_git: bool, commit_hash: str) -> list[SecretFinding]:
    findings = []
    lines = text.splitlines()

    for ln_idx, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            continue

        for rule in _SECRET_RULES:
            m = rule.pattern.search(line)
            if m:
                secret_value = m.group(rule.group) if rule.group < len(m.groups()) + 1 else m.group(0)
                entropy = _shannon_entropy(secret_value, _B64_CHARS)
                findings.append(SecretFinding(
                    file=filepath, line=ln_idx,
                    secret_type=rule.name, severity=rule.severity,
                    snippet=_redact(line.strip()[:80]),
                    entropy=round(entropy, 2),
                    in_git_history=in_git,
                    commit_hash=commit_hash,
                ))

        # High-entropy string detection
        if "=" in line or ":" in line:
            for ep in _ENTROPY_PATTERNS:
                for em in ep.finditer(line):
                    val = em.group(1)
                    charset = _B64_CHARS if re.match(r"[A-Za-z0-9+/=]", val) else _HEX_CHARS
                    entropy = _shannon_entropy(val, charset)
                    if entropy >= entropy_threshold:
                        findings.append(SecretFinding(
                            file=filepath, line=ln_idx,
                            secret_type="High-entropy string",
                            severity="medium",
                            snippet=_redact(line.strip()[:80]),
                            entropy=round(entropy, 2),
                            in_git_history=in_git,
                            commit_hash=commit_hash,
                        ))
                        break  # one per line

    return findings


def _scan_git_history(repo_path: str, depth: int, entropy_threshold: float) -> list[SecretFinding]:
    findings = []
    try:
        out = subprocess.run(
            ["git", "-C", repo_path, "log", f"-{depth}", "--pretty=format:%H", "--diff-filter=A"],
            capture_output=True, text=True, timeout=30,
        )
        commits = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        for commit in commits:
            diff_out = subprocess.run(
                ["git", "-C", repo_path, "show", commit, "--format="],
                capture_output=True, text=True, timeout=15,
            )
            for ln in diff_out.stdout.splitlines():
                if ln.startswith("+") and not ln.startswith("+++"):
                    findings.extend(_scan_text(ln[1:], f"git:{commit[:8]}", entropy_threshold, True, commit[:8]))
    except Exception:
        pass
    return findings


class SecretsScannerTool(BaseCallable):
    name = "secrets_scanner"
    description = (
        "Scan source code and git history for leaked secrets: AWS/GCP/Azure keys, "
        "GitHub/Slack/Stripe tokens, PEM private keys, connection strings, JWTs, "
        "and high-entropy strings. Complements vuln_scanner with credential-focused detection."
    )
    callable_type = CallableType.TOOL
    input_schema = SecretsScannerInput
    output_schema = SecretsScannerOutput

    async def _execute(self, input_data: SecretsScannerInput, context: object) -> SecretsScannerOutput:
        root = Path(input_data.path).expanduser().resolve()

        files: list[Path] = []
        if root.is_file():
            files = [root]
        else:
            for f in root.rglob("*"):
                if any(ex in f.parts for ex in input_data.exclude_dirs):
                    continue
                if (f.suffix in input_data.extensions or f.name in (".env", ".env.local", ".env.prod", ".env.production")) and f.is_file():
                    if len(files) >= input_data.max_files:
                        break
                    files.append(f)

        all_findings: list[SecretFinding] = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                all_findings.extend(_scan_text(text, str(f), input_data.entropy_threshold, False, ""))
            except Exception:
                pass

        git_commits_scanned = 0
        if input_data.scan_git_history:
            git_findings = _scan_git_history(str(root), input_data.git_depth, input_data.entropy_threshold)
            all_findings.extend(git_findings)
            git_commits_scanned = input_data.git_depth

        # Deduplicate by (file, line, type)
        seen = set()
        deduped = []
        for f in all_findings:
            key = (f.file, f.line, f.secret_type)
            if key not in seen:
                seen.add(key)
                deduped.append(f)

        deduped.sort(key=lambda x: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 4), x.file, x.line))

        counts = {"critical": 0, "high": 0}
        unique_types = []
        for f in deduped:
            if f.severity in counts:
                counts[f.severity] += 1
            if f.secret_type not in unique_types:
                unique_types.append(f.secret_type)

        return SecretsScannerOutput(
            scanned_files=len(files),
            git_commits_scanned=git_commits_scanned,
            findings=deduped,
            critical=counts["critical"],
            high=counts["high"],
            unique_secret_types=unique_types,
        )
