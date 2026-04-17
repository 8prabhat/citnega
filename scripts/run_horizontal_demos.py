#!/usr/bin/env python3
"""Run the three mandated horizontal workflow demos and emit evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import time


@dataclass(frozen=True)
class DemoScenario:
    id: str
    title: str
    requirement: str
    pytest_node: str


SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        id="WF-01",
        title="Code Refactor + Tests + Release Readiness",
        requirement="Code workflow with orchestration and release safety checks",
        pytest_node="tests/integration/test_orchestrator_golden.py::test_golden_multitool_success",
    ),
    DemoScenario(
        id="WF-02",
        title="Research/KB Synthesis and Retrieval",
        requirement="Research-style ingestion and retrieval persisted through KB",
        pytest_node=(
            "tests/integration/test_golden_scenarios.py::"
            "TestGS06KBIngestionAndRetrieval::test_add_kb_item_and_retrieve"
        ),
    ),
    DemoScenario(
        id="WF-03",
        title="Ops Diagnosis + Remediation + Verification",
        requirement="Security and release ops workflow with remediation guidance",
        pytest_node="tests/integration/test_p2_capabilities.py::test_p2_security_and_release_workflow",
    ),
)


def _run_pytest(node: str) -> dict[str, object]:
    cmd = [sys.executable, "-m", "pytest", node, "-q"]
    started = time.monotonic()
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "command": " ".join(cmd),
        "returncode": completed.returncode,
        "duration_ms": duration_ms,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-2000:],
        "passed": completed.returncode == 0,
    }


def _render_markdown(report: dict[str, object]) -> str:
    generated_at = str(report["generated_at"])
    overall_pass = bool(report["overall_pass"])
    lines = [
        "# Horizontal Workflow Demo Evidence",
        "",
        f"Generated at: {generated_at}",
        f"Overall pass: {'yes' if overall_pass else 'no'}",
        "",
        "| ID | Scenario | Requirement | Passed | Duration (ms) |",
        "|---|---|---|---|---:|",
    ]
    for item in report["scenarios"]:
        lines.append(
            "| {id} | {title} | {requirement} | {passed} | {duration_ms} |".format(
                id=item["id"],
                title=item["title"],
                requirement=item["requirement"],
                passed="yes" if item["result"]["passed"] else "no",
                duration_ms=item["result"]["duration_ms"],
            )
        )
    lines.append("")
    lines.append("## Command Output Tails")
    lines.append("")
    for item in report["scenarios"]:
        lines.append(f"### {item['id']} — {item['title']}")
        lines.append("")
        lines.append(f"`{item['result']['command']}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(item["result"]["stdout_tail"]).strip() or "(no stdout)")
        lines.append("```")
        stderr_tail = str(item["result"]["stderr_tail"]).strip()
        if stderr_tail:
            lines.append("")
            lines.append("stderr:")
            lines.append("```text")
            lines.append(stderr_tail)
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    evidence_dir = repo_root / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    scenarios: list[dict[str, object]] = []
    overall_pass = True
    for scenario in SCENARIOS:
        result = _run_pytest(scenario.pytest_node)
        overall_pass = overall_pass and bool(result["passed"])
        scenarios.append(
            {
                "id": scenario.id,
                "title": scenario.title,
                "requirement": scenario.requirement,
                "pytest_node": scenario.pytest_node,
                "result": result,
            }
        )

    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "overall_pass": overall_pass,
        "scenarios": scenarios,
    }

    json_latest = evidence_dir / "horizontal_demos_latest.json"
    md_latest = evidence_dir / "horizontal_demos_latest.md"
    json_ts = evidence_dir / f"horizontal_demos_{timestamp}.json"
    md_ts = evidence_dir / f"horizontal_demos_{timestamp}.md"

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
    print(f"overall_pass={overall_pass}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
