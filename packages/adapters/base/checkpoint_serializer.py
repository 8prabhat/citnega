"""
CheckpointSerializer — JSON-based checkpoint serialization shared by all adapters.

Each framework adapter stores framework-specific state (agent memory,
graph node pointers, crew state) inside the ``framework_state`` key of
the checkpoint blob.  The wrapper envelope contains correlation IDs so
the checkpoint can be restored to the correct session/run.

Blob format (gzip-compressed JSON)::

    {
        "schema_version": 1,
        "checkpoint_id":  "<uuid>",
        "session_id":     "...",
        "run_id":         "...",
        "framework_name": "...",
        "created_at":     "<iso8601>",
        "framework_state": { <adapter-specific dict> }
    }
"""

from __future__ import annotations

from datetime import UTC, datetime
import gzip
import json
from pathlib import Path
import uuid

from citnega.packages.protocol.models.checkpoints import CheckpointMeta

SCHEMA_VERSION = 1


class CheckpointSerializer:
    """Shared (de)serialization logic for all framework adapters."""

    def __init__(self, checkpoint_dir: Path, framework_name: str) -> None:
        self._dir = checkpoint_dir
        self._framework = framework_name

    def save(
        self,
        session_id: str,
        run_id: str,
        framework_state: dict[str, object],
    ) -> CheckpointMeta:
        """
        Serialize *framework_state* to a gzip-compressed JSON file.

        Returns CheckpointMeta with the file path and size.
        """
        checkpoint_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)

        blob = {
            "schema_version": SCHEMA_VERSION,
            "checkpoint_id": checkpoint_id,
            "session_id": session_id,
            "run_id": run_id,
            "framework_name": self._framework,
            "created_at": now.isoformat(),
            "framework_state": framework_state,
        }

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{checkpoint_id}.json.gz"
        raw = json.dumps(blob, default=str).encode("utf-8")
        compressed = gzip.compress(raw)
        path.write_bytes(compressed)

        state_summary = json.dumps(
            {
                k: v
                for k, v in framework_state.items()
                if isinstance(v, (str, int, float, bool, type(None)))
            },
            default=str,
        )[:256]

        return CheckpointMeta(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            run_id=run_id,
            created_at=now,
            framework_name=self._framework,
            file_path=str(path),
            size_bytes=len(compressed),
            state_summary=state_summary,
        )

    def load(self, file_path: str) -> dict[str, object]:
        """
        Deserialize a checkpoint blob.

        Returns the full blob dict (including ``framework_state``).
        Raises FileNotFoundError if the file does not exist.
        Raises ValueError on schema version mismatch.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {file_path}")

        compressed = path.read_bytes()
        raw = gzip.decompress(compressed)
        blob = json.loads(raw.decode("utf-8"))

        if blob.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Checkpoint schema_version mismatch: "
                f"expected {SCHEMA_VERSION}, got {blob.get('schema_version')!r}"
            )
        return blob
