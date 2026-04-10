"""Knowledge base Pydantic models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class KBSourceType(str, Enum):
    DOCUMENT         = "document"
    NOTE             = "note"
    SESSION_EXCERPT  = "session_excerpt"
    TOOL_OUTPUT      = "tool_output"
    GENERATED        = "generated"
    IMPORT           = "import"


class KBItem(BaseModel):
    item_id:           str
    title:             str
    content:           str
    source_type:       KBSourceType
    source_session_id: str | None = None
    source_run_id:     str | None = None
    tags:              list[str] = Field(default_factory=list)
    created_at:        datetime
    updated_at:        datetime
    content_hash:      str           # sha256 of content
    file_path:         str | None = None   # path if content stored on disk


class KBSearchResult(BaseModel):
    item:    KBItem
    score:   float    # FTS5 bm25 score (lower is better match)
    snippet: str      # highlighted excerpt
