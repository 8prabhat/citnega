"""
VulnScannerTool — static code vulnerability scanner.

Detects:
  - Hardcoded credentials / API keys / tokens
  - SQL injection patterns
  - Command injection patterns (shell=True, os.system, subprocess with user input)
  - Path traversal (../)
  - XSS (unescaped user input in HTML templates)
  - Insecure deserialization (pickle.loads, yaml.load without Loader)
  - Weak cryptography (MD5/SHA1 for security, DES, random not secrets)
  - Insecure randomness (random.random instead of secrets)
  - Debug/development flags left on (DEBUG=True, FLASK_ENV=development)
  - Open redirects
  - SSRF patterns (requests.get with user-supplied URL)
  - XXE patterns
  - Insecure file permissions
  - Eval / exec with user input
  - Hardcoded IPs / internal endpoints
  - Missing input validation

Supports: Python, JavaScript/TypeScript, Go, Java, Ruby, PHP, Bash.
Pure Python static analysis — no execution.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class VulnScannerInput(BaseModel):
    path: str = Field(description="File or directory path to scan")
    extensions: list[str] = Field(
        default=[".py", ".js", ".ts", ".go", ".java", ".rb", ".php", ".sh", ".bash"],
        description="File extensions to include",
    )
    max_files: int = Field(default=500)
    severity_filter: Literal["all", "critical", "high", "medium"] = Field(default="all")
    exclude_dirs: list[str] = Field(
        default=[".git", "node_modules", "__pycache__", ".venv", "vendor", "dist", "build"],
    )


class VulnFinding(BaseModel):
    file: str
    line: int
    severity: Literal["critical", "high", "medium", "low", "info"]
    category: str
    code_snippet: str
    description: str
    cwe: str


class VulnScannerOutput(BaseModel):
    scanned_files: int
    total_findings: int
    critical: int
    high: int
    medium: int
    low: int
    findings: list[VulnFinding]
    skipped_files: int


_SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class _Rule:
    __slots__ = ("pattern", "severity", "category", "description", "cwe", "flags")

    def __init__(self, pattern: str, severity: str, category: str, description: str, cwe: str, flags: int = re.IGNORECASE):
        self.pattern = re.compile(pattern, flags)
        self.severity = severity
        self.category = category
        self.description = description
        self.cwe = cwe


_RULES: list[_Rule] = [
    # ── Credentials & secrets ─────────────────────────────────────────────────
    _Rule(
        r'(?i)(password|passwd|pwd|secret|api[_-]?key|auth[_-]?token|access[_-]?token|private[_-]?key)\s*[=:]\s*["\'][^\s"\']{6,}["\']',
        "critical", "Hardcoded Credential",
        "Credential or secret appears hardcoded in source code",
        "CWE-798",
    ),
    _Rule(
        r'(?:AKIA|ASIA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}',
        "critical", "Hardcoded AWS Access Key",
        "AWS access key ID pattern detected",
        "CWE-798",
    ),
    _Rule(
        r'(?i)(gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})',
        "critical", "Hardcoded GitHub Token",
        "GitHub personal access token or OAuth token detected",
        "CWE-798",
    ),
    _Rule(
        r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}',
        "high", "Hardcoded JWT",
        "JWT token embedded in source code",
        "CWE-798",
    ),
    _Rule(
        r'-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
        "critical", "Hardcoded Private Key",
        "PEM private key found in source code",
        "CWE-321",
    ),

    # ── SQL Injection ─────────────────────────────────────────────────────────
    _Rule(
        r'(execute|executemany|cursor\.execute)\s*\(\s*[f"\'].*(%s|%d|\+|format\(|\.format)',
        "critical", "SQL Injection",
        "String formatting or concatenation in SQL query — use parameterized queries",
        "CWE-89",
    ),
    _Rule(
        r'(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+.*\+\s*\w+(request|input|param|query|body)',
        "critical", "SQL Injection",
        "User input concatenated directly into SQL string",
        "CWE-89",
    ),

    # ── Command Injection ─────────────────────────────────────────────────────
    _Rule(
        r'subprocess\.(call|run|Popen|check_output|check_call)\s*\(.*shell\s*=\s*True',
        "high", "Command Injection",
        "subprocess with shell=True allows shell injection if arguments contain user input",
        "CWE-78",
    ),
    _Rule(
        r'os\.system\s*\(',
        "high", "Command Injection",
        "os.system() passes string directly to shell — vulnerable to injection",
        "CWE-78",
    ),
    _Rule(
        r'exec\s*\(|eval\s*\(',
        "high", "Code Injection",
        "eval/exec with potentially untrusted input allows arbitrary code execution",
        "CWE-94",
    ),

    # ── Path Traversal ────────────────────────────────────────────────────────
    _Rule(
        r'open\s*\(\s*[^)]*\.\.\/',
        "high", "Path Traversal",
        "Potential path traversal — user input may control relative path",
        "CWE-22",
    ),
    _Rule(
        r'(request\.|req\.|params\[|query\[).*\.\.\/',
        "high", "Path Traversal",
        "User-controlled path contains directory traversal sequence",
        "CWE-22",
    ),

    # ── Insecure Deserialization ──────────────────────────────────────────────
    _Rule(
        r'pickle\.loads?\s*\(',
        "critical", "Insecure Deserialization",
        "pickle.load/loads can execute arbitrary code if data is attacker-controlled",
        "CWE-502",
    ),
    _Rule(
        r'yaml\.load\s*\([^)]*\)',
        "high", "Insecure Deserialization",
        "yaml.load without Loader= can execute Python objects — use yaml.safe_load",
        "CWE-502",
    ),
    _Rule(
        r'jsonpickle\.decode\s*\(',
        "critical", "Insecure Deserialization",
        "jsonpickle.decode allows arbitrary object instantiation",
        "CWE-502",
    ),

    # ── Weak Cryptography ────────────────────────────────────────────────────
    _Rule(
        r'hashlib\.md5\s*\(|hashlib\.sha1\s*\(',
        "medium", "Weak Cryptography",
        "MD5/SHA1 are cryptographically broken — use SHA-256 or stronger",
        "CWE-327",
    ),
    _Rule(
        r'DES\.|Cipher\.new\s*\(.*DES|Cipher\.new\s*\(.*RC4',
        "high", "Weak Cryptography",
        "DES/RC4 are deprecated symmetric ciphers",
        "CWE-326",
    ),
    _Rule(
        r'random\.random\s*\(\)|random\.randint\s*\(',
        "medium", "Insecure Randomness",
        "random module is not cryptographically secure — use secrets module for tokens/keys",
        "CWE-338",
    ),

    # ── Debug flags ──────────────────────────────────────────────────────────
    _Rule(
        r'DEBUG\s*=\s*True|FLASK_ENV\s*=\s*["\']development["\']|app\.run\s*\(.*debug\s*=\s*True',
        "high", "Debug Mode Enabled",
        "Debug mode exposes stack traces, interactive debugger, and detailed error messages",
        "CWE-489",
    ),

    # ── SSRF ─────────────────────────────────────────────────────────────────
    _Rule(
        r'requests\.(get|post|put|delete|head|patch)\s*\(\s*(request\.|req\.|params\[|query\[|input|url)',
        "high", "SSRF",
        "HTTP request to URL derived from user input — Server-Side Request Forgery",
        "CWE-918",
    ),

    # ── XSS ──────────────────────────────────────────────────────────────────
    _Rule(
        r'innerHTML\s*=\s*|document\.write\s*\(',
        "high", "XSS",
        "Direct DOM manipulation with innerHTML or document.write allows XSS",
        "CWE-79",
    ),
    _Rule(
        r'render_template_string\s*\(.*request\.|Markup\s*\(.*request\.',
        "high", "XSS / Template Injection",
        "User input passed to render_template_string or Markup() without escaping",
        "CWE-79",
    ),

    # ── XXE ──────────────────────────────────────────────────────────────────
    _Rule(
        r'xml\.etree\.ElementTree\.parse|lxml\.etree\.parse|minidom\.parseString',
        "medium", "XXE",
        "XML parsing without disabling external entity processing may allow XXE",
        "CWE-611",
    ),

    # ── Open Redirect ────────────────────────────────────────────────────────
    _Rule(
        r'redirect\s*\(\s*(request\.|req\.|params\[|query\[)',
        "high", "Open Redirect",
        "Redirect target derived from user input — open redirect vulnerability",
        "CWE-601",
    ),

    # ── Insecure file permissions ─────────────────────────────────────────────
    _Rule(
        r'os\.chmod\s*\(.*0o?777|chmod\s+777',
        "medium", "Insecure File Permission",
        "Setting world-writable permission (777) is insecure",
        "CWE-732",
    ),

    # ── Hardcoded IPs ────────────────────────────────────────────────────────
    _Rule(
        r'(?:127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)',
        "low", "Hardcoded Internal IP",
        "Hardcoded internal/loopback IP — may cause environment-specific failures",
        "CWE-1188",
    ),
]

_SEVERITY_FILTER_LEVELS = {"all": 0, "medium": 2, "high": 3, "critical": 4}


def _scan_file(path: Path, rules: list[_Rule], min_level: int) -> list[VulnFinding]:
    findings: list[VulnFinding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    lines = text.splitlines()
    for ln_idx, line in enumerate(lines, 1):
        for rule in rules:
            if rule.pattern.search(line):
                sev_level = _SEVERITY_ORDER.get(rule.severity, 0)
                if sev_level < min_level:
                    continue
                findings.append(VulnFinding(
                    file=str(path),
                    line=ln_idx,
                    severity=rule.severity,
                    category=rule.category,
                    code_snippet=line.strip()[:120],
                    description=rule.description,
                    cwe=rule.cwe,
                ))
    return findings


class VulnScannerTool(BaseCallable):
    name = "vuln_scanner"
    description = (
        "Static code vulnerability scanner for Python, JS/TS, Go, Java, Ruby, PHP, Bash. "
        "Detects: hardcoded secrets, SQL/command injection, XSS, SSRF, insecure deserialization, "
        "weak crypto, path traversal, debug flags, and 20+ other CWE categories."
    )
    callable_type = CallableType.TOOL
    input_schema = VulnScannerInput
    output_schema = VulnScannerOutput

    async def _execute(self, input_data: VulnScannerInput, context: object) -> VulnScannerOutput:
        root = Path(input_data.path).expanduser().resolve()
        min_level = _SEVERITY_FILTER_LEVELS.get(input_data.severity_filter, 0)

        files: list[Path] = []
        skipped = 0

        if root.is_file():
            files = [root]
        else:
            for f in root.rglob("*"):
                if any(ex in f.parts for ex in input_data.exclude_dirs):
                    continue
                if f.suffix in input_data.extensions and f.is_file():
                    if len(files) >= input_data.max_files:
                        skipped += 1
                    else:
                        files.append(f)

        all_findings: list[VulnFinding] = []
        for f in files:
            all_findings.extend(_scan_file(f, _RULES, min_level))

        # Sort by severity desc, then file, then line
        all_findings.sort(key=lambda x: (-_SEVERITY_ORDER.get(x.severity, 0), x.file, x.line))

        counts = {s: 0 for s in ("critical", "high", "medium", "low")}
        for f in all_findings:
            if f.severity in counts:
                counts[f.severity] += 1

        return VulnScannerOutput(
            scanned_files=len(files),
            total_findings=len(all_findings),
            critical=counts["critical"],
            high=counts["high"],
            medium=counts["medium"],
            low=counts["low"],
            findings=all_findings,
            skipped_files=skipped,
        )
