"""Secret bootstrap helpers for remote workers and benchmark publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import secrets


@dataclass(frozen=True)
class RemoteSecretBundle:
    generated_at: str
    envelope_signing_key_id: str
    envelope_signing_key: str
    auth_token: str
    benchmark_publication_key_id: str = ""
    benchmark_publication_signing_key: str = ""

    @property
    def includes_benchmark_publication_key(self) -> bool:
        return bool(self.benchmark_publication_key_id and self.benchmark_publication_signing_key)


def default_rotation_key_id(*, now: datetime | None = None) -> str:
    current = now or datetime.now(tz=UTC)
    return current.strftime("%Y-%m")


def build_remote_secret_bundle(
    *,
    envelope_signing_key_id: str,
    include_benchmark_publication_key: bool = True,
    benchmark_publication_key_id: str = "",
) -> RemoteSecretBundle:
    envelope_key_id = envelope_signing_key_id.strip() or default_rotation_key_id()
    publication_key_id = (
        benchmark_publication_key_id.strip()
        or f"benchmark-{envelope_key_id}"
    )
    return RemoteSecretBundle(
        generated_at=datetime.now(tz=UTC).isoformat(),
        envelope_signing_key_id=envelope_key_id,
        envelope_signing_key=secrets.token_urlsafe(48),
        auth_token=secrets.token_urlsafe(32),
        benchmark_publication_key_id=(
            publication_key_id if include_benchmark_publication_key else ""
        ),
        benchmark_publication_signing_key=(
            secrets.token_urlsafe(48) if include_benchmark_publication_key else ""
        ),
    )


def render_secret_bundle_text(bundle: RemoteSecretBundle) -> str:
    lines = [
        f"Generated at: {bundle.generated_at}",
        "",
        "Shell exports:",
        f"export CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY_ID={bundle.envelope_signing_key_id!r}",
        f"export CITNEGA_REMOTE_ENVELOPE_SIGNING_KEY={bundle.envelope_signing_key!r}",
        f"export CITNEGA_REMOTE_AUTH_TOKEN={bundle.auth_token!r}",
    ]
    if bundle.includes_benchmark_publication_key:
        lines.extend(
            [
                f"export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY_ID={bundle.benchmark_publication_key_id!r}",
                f"export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY={bundle.benchmark_publication_signing_key!r}",
            ]
        )

    lines.extend(
        [
            "",
            "settings.toml snippet:",
            "[remote]",
            f'envelope_signing_key_id = "{bundle.envelope_signing_key_id}"',
            'envelope_verification_keys = []',
            "# Prefer storing envelope_signing_key/auth_token in env or a secret manager.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_secret_bundle_json(bundle: RemoteSecretBundle) -> str:
    return json.dumps(
        {
            "generated_at": bundle.generated_at,
            "remote": {
                "envelope_signing_key_id": bundle.envelope_signing_key_id,
                "envelope_signing_key": bundle.envelope_signing_key,
                "auth_token": bundle.auth_token,
            },
            "benchmark_publication": (
                {
                    "signing_key_id": bundle.benchmark_publication_key_id,
                    "signing_key": bundle.benchmark_publication_signing_key,
                }
                if bundle.includes_benchmark_publication_key
                else None
            ),
        },
        indent=2,
        ensure_ascii=True,
    ) + "\n"
