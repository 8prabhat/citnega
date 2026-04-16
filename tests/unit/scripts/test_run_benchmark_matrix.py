"""Unit tests for benchmark publication helpers."""

from __future__ import annotations

from pathlib import Path

from scripts import run_benchmark_matrix as benchmark_script


def _report() -> dict[str, object]:
    return {
        "generated_at": "2026-04-15T00:00:00+00:00",
        "overall_pass": True,
        "threshold_gate_pass": True,
        "previous_run_generated_at": "2026-04-14T00:00:00+00:00",
        "checks": [
            {
                "id": "BM-01",
                "duration_ms": 100,
                "trend": "flat",
                "delta_vs_previous_pct": 0.0,
                "meets_threshold": True,
            }
        ],
    }


def test_build_publication_payload_includes_branch_metadata_and_digests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_path = tmp_path / "benchmark.json"
    history_path = tmp_path / "benchmark_history.jsonl"
    report_path.write_text("{}\n", encoding="utf-8")
    history_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("CITNEGA_BENCHMARK_PUBLICATION_BRANCH", "feature/remote-mtls")
    monkeypatch.setenv("CITNEGA_BENCHMARK_PUBLICATION_GIT_REF", "refs/heads/feature/remote-mtls")
    monkeypatch.setenv("CITNEGA_BENCHMARK_PUBLICATION_GIT_SHA", "abc123")
    monkeypatch.setenv("CITNEGA_BENCHMARK_PUBLICATION_REPOSITORY", "acme/citnega")

    payload = benchmark_script._build_publication_payload(
        report=_report(),
        report_path=report_path,
        history_path=history_path,
        benchmark_label="ubuntu-latest-py3.12",
        history_entries=[dict(_report(), benchmark_label="ubuntu-latest-py3.12")],
    )

    assert payload["branch_name"] == "feature/remote-mtls"
    assert payload["branch_slug"] == "feature-remote-mtls"
    assert payload["repository"] == "acme/citnega"
    assert payload["report_sha256"] == benchmark_script._sha256_file(report_path)
    assert payload["history_sha256"] == benchmark_script._sha256_file(history_path)


def test_wrap_signed_publication_generates_stable_hmac_signature() -> None:
    payload = {"generated_at": "2026-04-15T00:00:00+00:00", "benchmark_label": "lane"}

    signed = benchmark_script._wrap_signed_publication(
        payload=payload,
        signing_key="secret",
        signing_key_id="benchmark-2026-04",
    )

    assert signed["signature_algorithm"] == "hmac-sha256"
    assert signed["signature_key_id"] == "benchmark-2026-04"
    assert signed["signature"]
    assert signed["payload"] == payload


def test_render_publication_markdown_includes_signature_metadata() -> None:
    publication = {
        "signature_algorithm": "hmac-sha256",
        "signature_key_id": "benchmark-2026-04",
        "signature": "deadbeef",
        "payload": {
            "generated_at": "2026-04-15T00:00:00+00:00",
            "branch_name": "main",
            "benchmark_label": "lane",
            "repository": "acme/citnega",
            "git_sha": "abc123",
            "ci_run_url": "",
            "report_sha256": "r" * 64,
            "history_sha256": "h" * 64,
            "check_summaries": [
                {
                    "id": "BM-01",
                    "duration_ms": 100,
                    "trend": "flat",
                    "delta_vs_previous_pct": 0.0,
                    "meets_threshold": True,
                }
            ],
        },
    }

    md = benchmark_script._render_publication_markdown(publication)

    assert "Signature key id: benchmark-2026-04" in md
    assert "| BM-01 | 100 | flat | 0.0% | yes |" in md
