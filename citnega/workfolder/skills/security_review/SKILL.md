---
name: security_review
description: Comprehensive security review protocol for code changes and file systems.
triggers:
  - security review
  - audit
  - scan for secrets
  - check vulnerabilities
  - security audit
  - penetration
  - pen test
preferred_tools:
  - vuln_scanner
  - secrets_scanner
  - hash_integrity
  - os_fingerprint
  - process_inspector
preferred_agents:
  - security_agent
supported_modes:
  - review
  - code
tags:
  - security
  - audit
---

## Security Review Protocol

When this skill is active, follow these steps for every security-related request:

**Step 1 — Static code analysis:**
- Invoke `security_agent` on the working directory or changed files.
- Run `vuln_scanner` to detect: hardcoded credentials, SQL injection, unsafe `eval()`, `subprocess.shell=True`, `verify=False` in HTTP clients, insecure deserialization.
- Run `secrets_scanner` on any `.env`, config, or credential files.

**Step 2 — Integrity checks:**
- Run `hash_integrity` on critical files if a baseline exists.
- Check for unexpected SUID bits or world-writable files if on Linux.

**Step 3 — System posture (if applicable):**
- Run `os_fingerprint` to confirm the target OS and architecture.
- Run `process_inspector` if suspicious processes should be checked.

**Step 4 — Report findings by severity:**
Structure every finding as:

**[SEVERITY] file.py:line — brief description**
- Risk: what an attacker could do if exploited
- Recommendation: concrete remediation step

Severity levels: CRITICAL (data exfiltration/RCE) | HIGH (privilege escalation/auth bypass) | MEDIUM (info leak/logic flaw) | LOW (defense-in-depth improvement) | INFO (observation)

**Never** mark a finding CRITICAL without explaining the specific exploit path. **Always** include file and line number citations from tool output.
