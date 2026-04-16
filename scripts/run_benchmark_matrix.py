#!/usr/bin/env python3
"""Run a reproducible benchmark sample and write matrix evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


@dataclass(frozen=True)
class BenchmarkCheck:
    id: str
    description: str
    command: list[str]


CHECKS: tuple[BenchmarkCheck, ...] = (
    BenchmarkCheck(
        id="BM-01",
        description="repo_map cache-hit path",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/tools/test_p1_tools.py::test_repo_map_uses_cache_on_second_run",
            "-q",
        ],
    ),
    BenchmarkCheck(
        id="BM-02",
        description="test_matrix cache-hit discovery path",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/tools/test_p1_tools.py::test_test_matrix_uses_cache_for_discovery",
            "-q",
        ],
    ),
    BenchmarkCheck(
        id="BM-03",
        description="security_agent static-scan cache-hit path",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/agents/test_p2_agents.py::test_security_agent_uses_cache_on_second_static_scan",
            "-q",
        ],
    ),
    BenchmarkCheck(
        id="BM-04",
        description="reference remote worker service dispatch path",
        command=[
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/runtime/test_remote_service.py::test_remote_worker_service_roundtrip_invokes_callable",
            "-q",
        ],
    ),
)

_HISTORY_FILENAME = "benchmark_matrix_history.jsonl"
_PUBLICATION_HISTORY_FILENAME = "benchmark_publication_history.jsonl"


def _run_check(check: BenchmarkCheck) -> dict[str, object]:
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
        "stdout_tail": completed.stdout[-2500:],
        "stderr_tail": completed.stderr[-1500:],
    }


def _load_thresholds(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"default": {"checks": {}}, "lanes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_lane_thresholds(
    *,
    benchmark_label: str,
    thresholds: dict[str, object],
) -> dict[str, dict[str, int]]:
    default_checks = (
        thresholds.get("default", {}).get("checks", {})
        if isinstance(thresholds.get("default", {}), dict)
        else {}
    )
    lane_checks = {}
    lanes = thresholds.get("lanes", {})
    if isinstance(lanes, dict):
        lane = lanes.get(benchmark_label, {})
        if isinstance(lane, dict):
            lane_checks = lane.get("checks", {})

    resolved: dict[str, dict[str, int]] = {}
    for source in (default_checks, lane_checks):
        if not isinstance(source, dict):
            continue
        for check_id, policy in source.items():
            if not isinstance(policy, dict):
                continue
            baseline_ms = int(policy.get("baseline_ms", 0))
            max_regression_pct = int(policy.get("max_regression_pct", 0))
            resolved[str(check_id)] = {
                "baseline_ms": baseline_ms,
                "max_regression_pct": max_regression_pct,
            }
    return resolved


def _apply_threshold_policy(
    *,
    results: list[dict[str, object]],
    policies: dict[str, dict[str, int]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for item in results:
        policy = policies.get(str(item["id"]), {})
        baseline_ms = int(policy.get("baseline_ms", 0))
        max_regression_pct = int(policy.get("max_regression_pct", 0))
        threshold_ms = (
            round(baseline_ms * (1 + (max_regression_pct / 100.0)))
            if baseline_ms > 0
            else 0
        )
        meets_threshold = threshold_ms == 0 or int(item["duration_ms"]) <= threshold_ms
        item = dict(item)
        item["baseline_ms"] = baseline_ms
        item["max_regression_pct"] = max_regression_pct
        item["threshold_ms"] = threshold_ms
        item["meets_threshold"] = meets_threshold
        enriched.append(item)
    return enriched


def _load_history_entries(*, history_path: Path, evidence_dir: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    else:
        for artifact in sorted(evidence_dir.glob("benchmark_matrix_*.json")):
            if artifact.name == "benchmark_matrix_latest.json":
                continue
            try:
                payload = json.loads(artifact.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    entries.sort(key=lambda item: str(item.get("generated_at", "")))
    return entries


def _apply_history_delta(
    *,
    results: list[dict[str, object]],
    previous_report: dict[str, object] | None,
) -> list[dict[str, object]]:
    previous_checks = {}
    previous_generated_at = ""
    if isinstance(previous_report, dict):
        previous_generated_at = str(previous_report.get("generated_at", "")).strip()
        raw_checks = previous_report.get("checks", [])
        if isinstance(raw_checks, list):
            previous_checks = {
                str(item.get("id", "")): item
                for item in raw_checks
                if isinstance(item, dict)
            }

    enriched: list[dict[str, object]] = []
    for item in results:
        previous_item = previous_checks.get(str(item["id"]))
        previous_duration_ms: int | None = None
        delta_vs_previous_ms: int | None = None
        delta_vs_previous_pct: float | None = None
        trend = "baseline"
        if previous_item is not None:
            previous_duration_ms = int(previous_item.get("duration_ms", 0))
            delta_vs_previous_ms = int(item["duration_ms"]) - previous_duration_ms
            if previous_duration_ms > 0:
                delta_vs_previous_pct = round(
                    (delta_vs_previous_ms / previous_duration_ms) * 100,
                    2,
                )
            if delta_vs_previous_ms < 0:
                trend = "improved"
            elif delta_vs_previous_ms > 0:
                trend = "regressed"
            else:
                trend = "flat"

        item = dict(item)
        item["previous_generated_at"] = previous_generated_at
        item["previous_duration_ms"] = previous_duration_ms
        item["delta_vs_previous_ms"] = delta_vs_previous_ms
        item["delta_vs_previous_pct"] = delta_vs_previous_pct
        item["trend"] = trend
        enriched.append(item)
    return enriched


def _find_previous_report(
    *,
    history_entries: list[dict[str, object]],
    benchmark_label: str,
) -> dict[str, object] | None:
    for entry in reversed(history_entries):
        if str(entry.get("benchmark_label", "")).strip() == benchmark_label:
            return entry
    return None


def _append_history(history_path: Path, report: dict[str, object]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(report, ensure_ascii=True) + "\n")


def _append_publication_history(history_path: Path, publication: dict[str, object]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(publication, ensure_ascii=True) + "\n")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _resolve_bool_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "local"


def _git_value(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _resolve_publication_metadata() -> dict[str, str]:
    branch_name = (
        os.environ.get("CITNEGA_BENCHMARK_PUBLICATION_BRANCH", "").strip()
        or os.environ.get("GITHUB_REF_NAME", "").strip()
        or _git_value("rev-parse", "--abbrev-ref", "HEAD")
    )
    git_ref = (
        os.environ.get("CITNEGA_BENCHMARK_PUBLICATION_GIT_REF", "").strip()
        or os.environ.get("GITHUB_REF", "").strip()
    )
    git_sha = (
        os.environ.get("CITNEGA_BENCHMARK_PUBLICATION_GIT_SHA", "").strip()
        or os.environ.get("GITHUB_SHA", "").strip()
        or _git_value("rev-parse", "HEAD")
    )
    repository = (
        os.environ.get("CITNEGA_BENCHMARK_PUBLICATION_REPOSITORY", "").strip()
        or os.environ.get("GITHUB_REPOSITORY", "").strip()
    )
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "").strip()
    server_url = os.environ.get("GITHUB_SERVER_URL", "").strip() or "https://github.com"
    run_url = ""
    if repository and run_id:
        run_url = f"{server_url}/{repository}/actions/runs/{run_id}"
    return {
        "branch_name": branch_name,
        "branch_slug": _slugify(branch_name),
        "git_ref": git_ref,
        "git_sha": git_sha,
        "repository": repository,
        "ci_run_id": run_id,
        "ci_run_attempt": run_attempt,
        "ci_run_url": run_url,
    }


def _build_publication_payload(
    *,
    report: dict[str, object],
    report_path: Path,
    history_path: Path,
    benchmark_label: str,
    history_entries: list[dict[str, object]],
) -> dict[str, object]:
    metadata = _resolve_publication_metadata()
    lane_tail: list[dict[str, object]] = []
    for entry in history_entries[-10:]:
        if str(entry.get("benchmark_label", "")).strip() != benchmark_label:
            continue
        lane_tail.append(
            {
                "generated_at": entry.get("generated_at", ""),
                "overall_pass": bool(entry.get("overall_pass", False)),
                "threshold_gate_pass": bool(entry.get("threshold_gate_pass", False)),
                "checks": [
                    {
                        "id": check.get("id", ""),
                        "duration_ms": int(check.get("duration_ms", 0)),
                        "trend": check.get("trend", "baseline"),
                    }
                    for check in entry.get("checks", [])
                    if isinstance(check, dict)
                ],
            }
        )

    return {
        "kind": "benchmark_publication",
        "generated_at": report["generated_at"],
        "benchmark_label": benchmark_label,
        "branch_name": metadata["branch_name"],
        "branch_slug": metadata["branch_slug"],
        "git_ref": metadata["git_ref"],
        "git_sha": metadata["git_sha"],
        "repository": metadata["repository"],
        "ci_run_id": metadata["ci_run_id"],
        "ci_run_attempt": metadata["ci_run_attempt"],
        "ci_run_url": metadata["ci_run_url"],
        "report_path": str(report_path),
        "history_path": str(history_path),
        "report_sha256": _sha256_file(report_path),
        "history_sha256": _sha256_file(history_path),
        "overall_pass": bool(report["overall_pass"]),
        "threshold_gate_pass": bool(report["threshold_gate_pass"]),
        "previous_run_generated_at": report.get("previous_run_generated_at", ""),
        "check_summaries": [
            {
                "id": check["id"],
                "duration_ms": check["duration_ms"],
                "trend": check["trend"],
                "delta_vs_previous_pct": check["delta_vs_previous_pct"],
                "meets_threshold": check["meets_threshold"],
            }
            for check in report["checks"]
        ],
        "lane_history_tail": lane_tail,
    }


def _wrap_signed_publication(
    *,
    payload: dict[str, object],
    signing_key: str,
    signing_key_id: str,
) -> dict[str, object]:
    signature = hmac.new(
        signing_key.encode("utf-8"),
        _canonical_json_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    return {
        "signature_algorithm": "hmac-sha256",
        "signature_key_id": signing_key_id,
        "signature": signature,
        "payload": payload,
    }


def _render_publication_markdown(publication: dict[str, object]) -> str:
    payload = publication["payload"]
    lines = [
        "# Benchmark Publication",
        "",
        f"Generated at: {payload['generated_at']}",
        f"Branch: {payload['branch_name'] or 'local'}",
        f"Benchmark label: {payload['benchmark_label']}",
        f"Repository: {payload['repository'] or 'local'}",
        f"Git SHA: {payload['git_sha'] or 'unknown'}",
        f"Run URL: {payload['ci_run_url'] or 'n/a'}",
        f"Signature key id: {publication['signature_key_id']}",
        f"Signature algorithm: {publication['signature_algorithm']}",
        f"Report digest: {payload['report_sha256']}",
        f"History digest: {payload['history_sha256']}",
        "",
        "| ID | Duration (ms) | Trend | Delta vs Prev | Threshold Gate |",
        "|---|---:|---|---:|---|",
    ]
    for check in payload["check_summaries"]:
        delta = check["delta_vs_previous_pct"]
        delta_text = "n/a" if delta is None else f"{delta}%"
        lines.append(
            f"| {check['id']} | {check['duration_ms']} | {check['trend']} | "
            f"{delta_text} | {'yes' if check['meets_threshold'] else 'no'} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _render_markdown(report: dict[str, object]) -> str:
    previous_run_at = str(report.get("previous_run_generated_at", "")).strip()
    lines = [
        "# Benchmark Matrix Evidence",
        "",
        f"Generated at: {report['generated_at']}",
        f"Benchmark label: {report['benchmark_label']}",
        f"Platform: {report['platform']}",
        f"Python: {report['python_version']}",
        f"Overall pass: {'yes' if report['overall_pass'] else 'no'}",
        f"Threshold gate pass: {'yes' if report['threshold_gate_pass'] else 'no'}",
        f"Threshold policy: {report['thresholds_path']}",
        f"History file: {report['history_path']}",
        f"Previous lane run: {previous_run_at or 'none'}",
        "",
        "| ID | Description | Passed | Threshold Gate | Duration (ms) | Previous | Delta vs Prev | Trend | Baseline | Threshold | Max Regression |",
        "|---|---|---|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for check in report["checks"]:
        delta_text = "-"
        if check["delta_vs_previous_ms"] is not None:
            delta_pct = check["delta_vs_previous_pct"]
            pct_text = "n/a" if delta_pct is None else f"{delta_pct}%"
            delta_text = f"{check['delta_vs_previous_ms']} ({pct_text})"
        lines.append(
            f"| {check['id']} | {check['description']} | "
            f"{'yes' if check['passed'] else 'no'} | "
            f"{'yes' if check['meets_threshold'] else 'no'} | "
            f"{check['duration_ms']} | {check['previous_duration_ms'] or '-'} | "
            f"{delta_text} | {check['trend']} | {check['baseline_ms']} | "
            f"{check['threshold_ms']} | {check['max_regression_pct']}% |"
        )

    lines.append("")
    lines.append("## Command Output Tails")
    lines.append("")
    for check in report["checks"]:
        lines.append(f"### {check['id']} — {check['description']}")
        lines.append("")
        lines.append(f"`{check['command']}`")
        lines.append("")
        lines.append("```text")
        lines.append(str(check["stdout_tail"]).strip() or "(no stdout)")
        lines.append("```")
        stderr_tail = str(check["stderr_tail"]).strip()
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
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    benchmark_label = (
        os.environ.get("CITNEGA_BENCHMARK_LABEL", "").strip()
        or f"{platform.system().lower()}-py{platform.python_version()}"
    )
    thresholds_path = Path(
        os.environ.get(
            "CITNEGA_BENCHMARK_THRESHOLDS_PATH",
            str(evidence_dir / "benchmark_thresholds.json"),
        )
    )
    history_path = Path(
        os.environ.get(
            "CITNEGA_BENCHMARK_HISTORY_PATH",
            str(evidence_dir / _HISTORY_FILENAME),
        )
    )
    publication_history_path = Path(
        os.environ.get(
            "CITNEGA_BENCHMARK_PUBLICATION_HISTORY_PATH",
            str(evidence_dir / _PUBLICATION_HISTORY_FILENAME),
        )
    )
    publication_signing_key = os.environ.get(
        "CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY",
        "",
    ).strip()
    publication_signing_key_id = os.environ.get(
        "CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY_ID",
        "",
    ).strip()
    require_publication_signature = _resolve_bool_env(
        "CITNEGA_BENCHMARK_PUBLICATION_REQUIRE_SIGNATURE"
    )
    if require_publication_signature and not publication_signing_key:
        raise SystemExit(
            "Benchmark publication signing key is required when "
            "CITNEGA_BENCHMARK_PUBLICATION_REQUIRE_SIGNATURE=true."
        )
    if publication_signing_key and not publication_signing_key_id:
        raise SystemExit(
            "Benchmark publication signing key id is required when a signing key is configured."
        )
    thresholds = _load_thresholds(thresholds_path)
    policies = _resolve_lane_thresholds(
        benchmark_label=benchmark_label,
        thresholds=thresholds,
    )
    history_entries = _load_history_entries(history_path=history_path, evidence_dir=evidence_dir)
    previous_report = _find_previous_report(
        history_entries=history_entries,
        benchmark_label=benchmark_label,
    )

    checks = _apply_threshold_policy(
        results=[_run_check(check) for check in CHECKS],
        policies=policies,
    )
    checks = _apply_history_delta(results=checks, previous_report=previous_report)
    overall_pass = all(bool(item["passed"]) for item in checks)
    threshold_gate_pass = overall_pass and all(bool(item["meets_threshold"]) for item in checks)
    previous_run_generated_at = (
        str(previous_report.get("generated_at", "")).strip()
        if previous_report is not None
        else ""
    )

    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "benchmark_label": benchmark_label,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "overall_pass": overall_pass,
        "threshold_gate_pass": threshold_gate_pass,
        "thresholds_path": str(thresholds_path),
        "history_path": str(history_path),
        "history_entries_loaded": len(history_entries),
        "history_entries_written": len(history_entries) + 1,
        "previous_run_generated_at": previous_run_generated_at,
        "checks": checks,
    }

    json_latest = evidence_dir / "benchmark_matrix_latest.json"
    md_latest = evidence_dir / "benchmark_matrix_latest.md"
    json_ts = evidence_dir / f"benchmark_matrix_{stamp}_{benchmark_label}.json"
    md_ts = evidence_dir / f"benchmark_matrix_{stamp}_{benchmark_label}.md"
    publication_json_latest = evidence_dir / "benchmark_publication_latest.json"
    publication_md_latest = evidence_dir / "benchmark_publication_latest.md"
    publication_json_ts = evidence_dir / f"benchmark_publication_{stamp}_{benchmark_label}.json"
    publication_md_ts = evidence_dir / f"benchmark_publication_{stamp}_{benchmark_label}.md"

    payload = json.dumps(report, indent=2, ensure_ascii=True)
    json_latest.write_text(payload + "\n", encoding="utf-8")
    json_ts.write_text(payload + "\n", encoding="utf-8")
    md = _render_markdown(report)
    md_latest.write_text(md, encoding="utf-8")
    md_ts.write_text(md, encoding="utf-8")
    _append_history(history_path, report)
    updated_history_entries = [*history_entries, report]
    publication_payload = _build_publication_payload(
        report=report,
        report_path=json_latest,
        history_path=history_path,
        benchmark_label=benchmark_label,
        history_entries=updated_history_entries,
    )
    if publication_signing_key:
        publication = _wrap_signed_publication(
            payload=publication_payload,
            signing_key=publication_signing_key,
            signing_key_id=publication_signing_key_id,
        )
    else:
        publication = {
            "signature_algorithm": "",
            "signature_key_id": "",
            "signature": "",
            "payload": publication_payload,
        }
    publication_json = json.dumps(publication, indent=2, ensure_ascii=True)
    publication_json_latest.write_text(publication_json + "\n", encoding="utf-8")
    publication_json_ts.write_text(publication_json + "\n", encoding="utf-8")
    publication_md = _render_publication_markdown(publication)
    publication_md_latest.write_text(publication_md, encoding="utf-8")
    publication_md_ts.write_text(publication_md, encoding="utf-8")
    _append_publication_history(publication_history_path, publication)

    print(f"Wrote: {json_latest}")
    print(f"Wrote: {md_latest}")
    print(f"Wrote: {json_ts}")
    print(f"Wrote: {md_ts}")
    print(f"Wrote: {publication_json_latest}")
    print(f"Wrote: {publication_md_latest}")
    print(f"Wrote: {publication_json_ts}")
    print(f"Wrote: {publication_md_ts}")
    print(f"Appended history: {history_path}")
    print(f"Appended publication history: {publication_history_path}")
    print(f"overall_pass={overall_pass}")
    print(f"threshold_gate_pass={threshold_gate_pass}")
    return 0 if threshold_gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
