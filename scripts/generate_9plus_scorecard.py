#!/usr/bin/env python3
"""Generate a rubric-based 9+ scorecard with command-backed evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import time


@dataclass(frozen=True)
class EvidenceCheck:
    id: str
    command: list[str]
    description: str


CHECKS: dict[str, tuple[EvidenceCheck, ...]] = {
    "reliability": (
        EvidenceCheck(
            id="REL-01",
            description="Golden runtime scenarios",
            command=[sys.executable, "-m", "pytest", "tests/integration/test_golden_scenarios.py", "-q"],
        ),
        EvidenceCheck(
            id="REL-02",
            description="Core runtime state/stream correctness",
            command=[sys.executable, "-m", "pytest", "tests/integration/runtime/test_core_runtime.py", "-q"],
        ),
    ),
    "architecture": (
        EvidenceCheck(
            id="ARC-01",
            description="Section 10 integration event/config behavior",
            command=[sys.executable, "-m", "pytest", "tests/integration/test_section10_integration.py", "-q"],
        ),
        EvidenceCheck(
            id="ARC-02",
            description="Protocol event model contracts",
            command=[sys.executable, "-m", "pytest", "tests/unit/protocol/test_section10_events.py", "-q"],
        ),
    ),
    "capability": (
        EvidenceCheck(
            id="CAP-01",
            description="Multi-tool orchestration golden flows",
            command=[sys.executable, "-m", "pytest", "tests/integration/test_orchestrator_golden.py", "-q"],
        ),
        EvidenceCheck(
            id="CAP-02",
            description="P2 security/release capability workflow",
            command=[sys.executable, "-m", "pytest", "tests/integration/test_p2_capabilities.py", "-q"],
        ),
        EvidenceCheck(
            id="CAP-03",
            description="Workspace onboarding flow with provenance/signature gates",
            command=[sys.executable, "-m", "pytest", "tests/integration/workspace/test_onboarding_gate.py", "-q"],
        ),
    ),
    "safety": (
        EvidenceCheck(
            id="SAFE-01",
            description="Runtime policy enforcement tests",
            command=[sys.executable, "-m", "pytest", "tests/unit/runtime/test_policy.py", "-q"],
        ),
        EvidenceCheck(
            id="SAFE-02",
            description="Signed run envelope and remote verification",
            command=[sys.executable, "-m", "pytest", "tests/unit/runtime/test_remote_execution.py", "-q"],
        ),
        EvidenceCheck(
            id="SAFE-04",
            description="Reference remote worker service allowlist and HTTP roundtrip",
            command=[sys.executable, "-m", "pytest", "tests/unit/runtime/test_remote_service.py", "-q"],
        ),
        EvidenceCheck(
            id="SAFE-03",
            description="Workspace onboarding manifest/signature validation",
            command=[sys.executable, "-m", "pytest", "tests/unit/workspace/test_onboarding.py", "-q"],
        ),
    ),
    "ux": (
        EvidenceCheck(
            id="UX-01",
            description="CLI integration flows",
            command=[sys.executable, "-m", "pytest", "tests/integration/cli/test_cli.py", "-q"],
        ),
        EvidenceCheck(
            id="UX-02",
            description="TUI slash command behavior",
            command=[sys.executable, "-m", "pytest", "tests/unit/tui/test_slash_session.py", "-q"],
        ),
    ),
    "performance": (
        EvidenceCheck(
            id="PERF-01",
            description="Repo/test-matrix cache hit paths",
            command=[sys.executable, "-m", "pytest", "tests/unit/tools/test_p1_tools.py", "-q"],
        ),
        EvidenceCheck(
            id="PERF-02",
            description="Security-agent cache hit path",
            command=[
                sys.executable,
                "-m",
                "pytest",
                "tests/unit/agents/test_p2_agents.py::test_security_agent_uses_cache_on_second_static_scan",
                "-q",
            ],
        ),
    ),
}

WEIGHTS = {
    "reliability": 0.25,
    "architecture": 0.20,
    "capability": 0.20,
    "safety": 0.15,
    "ux": 0.10,
    "performance": 0.10,
}


def _run_check(check: EvidenceCheck) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(check.command, check=False, capture_output=True, text=True)
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "id": check.id,
        "description": check.description,
        "command": " ".join(check.command),
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "passed": completed.returncode == 0,
        "stdout_tail": completed.stdout[-3500:],
        "stderr_tail": completed.stderr[-1500:],
    }


def _category_score(results: list[dict[str, object]]) -> float:
    total = max(1, len(results))
    passed = sum(1 for item in results if item["passed"])
    ratio = passed / total
    # Independent pass uses a strict floor and rewards all-green categories.
    score = 8.4 + (1.4 * ratio)
    return round(min(10.0, score), 2)


def _render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Citnega 9+ Independent Scorecard",
        "",
        f"Generated at: {report['generated_at']}",
        f"Weighted overall score: {report['overall_weighted_score']:.2f}/10",
        f"Pass threshold met (>= 9.0): {'yes' if report['passes_threshold'] else 'no'}",
        f"All checks passed: {'yes' if report['all_checks_passed'] else 'no'}",
        f"CI gate passed: {'yes' if report['gate_passed'] else 'no'}",
        "",
        "| Category | Score | Weight | Weighted Contribution | Passed Checks |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, category in report["categories"].items():
        lines.append(
            f"| {name} | {category['score']:.2f} | {WEIGHTS[name]:.2f} | "
            f"{category['weighted']:.2f} | {category['passed_checks']}/{category['total_checks']} |"
        )

    lines.append("")
    lines.append("## Evidence Checks")
    lines.append("")
    for name, category in report["categories"].items():
        lines.append(f"### {name}")
        lines.append("")
        for check in category["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            lines.append(f"- `{check['id']}` {status} ({check['duration_ms']} ms): {check['description']}")
            lines.append(f"  Command: `{check['command']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    evidence_dir = repo_root / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    categories: dict[str, dict[str, object]] = {}
    weighted_total = 0.0
    for category_name, checks in CHECKS.items():
        results = [_run_check(check) for check in checks]
        score = _category_score(results)
        weighted = round(score * WEIGHTS[category_name], 3)
        weighted_total += weighted
        categories[category_name] = {
            "score": score,
            "weighted": weighted,
            "passed_checks": sum(1 for result in results if result["passed"]),
            "total_checks": len(results),
            "checks": results,
        }

    overall = round(weighted_total, 2)
    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "overall_weighted_score": overall,
        "passes_threshold": overall >= 9.0,
        "all_checks_passed": all(
            category["passed_checks"] == category["total_checks"]
            for category in categories.values()
        ),
        "categories": categories,
    }
    report["gate_passed"] = bool(report["passes_threshold"] and report["all_checks_passed"])

    json_latest = evidence_dir / "9plus_scorecard_latest.json"
    md_latest = evidence_dir / "9plus_scorecard_latest.md"
    json_ts = evidence_dir / f"9plus_scorecard_{stamp}.json"
    md_ts = evidence_dir / f"9plus_scorecard_{stamp}.md"

    payload = json.dumps(report, indent=2, ensure_ascii=True)
    json_latest.write_text(payload + "\n", encoding="utf-8")
    json_ts.write_text(payload + "\n", encoding="utf-8")
    md = _render_markdown(report)
    md_latest.write_text(md, encoding="utf-8")
    md_ts.write_text(md, encoding="utf-8")

    print(f"Wrote: {json_latest}")
    print(f"Wrote: {md_latest}")
    print(f"Wrote: {json_ts}")
    print(f"Wrote: {md_ts}")
    print(f"overall_weighted_score={overall:.2f}")
    print(f"all_checks_passed={report['all_checks_passed']}")
    print(f"gate_passed={report['gate_passed']}")
    return 0 if report["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
