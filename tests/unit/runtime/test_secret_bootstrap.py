"""Unit tests for remote secret bootstrap helpers."""

from __future__ import annotations

import json

from citnega.packages.runtime.remote.secret_bootstrap import (
    build_remote_secret_bundle,
    render_secret_bundle_json,
    render_secret_bundle_text,
)


def test_build_remote_secret_bundle_includes_publication_key_by_default() -> None:
    bundle = build_remote_secret_bundle(envelope_signing_key_id="2026-04")

    assert bundle.envelope_signing_key_id == "2026-04"
    assert bundle.envelope_signing_key
    assert bundle.auth_token
    assert bundle.benchmark_publication_key_id == "benchmark-2026-04"
    assert bundle.benchmark_publication_signing_key


def test_render_secret_bundle_json_is_machine_readable() -> None:
    bundle = build_remote_secret_bundle(
        envelope_signing_key_id="2026-04",
        include_benchmark_publication_key=False,
    )

    payload = json.loads(render_secret_bundle_json(bundle))

    assert payload["remote"]["envelope_signing_key_id"] == "2026-04"
    assert payload["benchmark_publication"] is None


def test_render_secret_bundle_text_includes_exports_and_toml_snippet() -> None:
    bundle = build_remote_secret_bundle(envelope_signing_key_id="2026-04")

    text = render_secret_bundle_text(bundle)

    assert "export CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID='2026-04'" in text
    assert "[remote]" in text
    assert 'envelope_signing_key_id = "2026-04"' in text
