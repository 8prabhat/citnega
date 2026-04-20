"""translate_text — translate text to a target language using deep-translator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

# BCP-47 language code samples shown in description
_LANG_EXAMPLES = "en, fr, de, es, it, pt, nl, ja, zh-CN, zh-TW, ko, ar, hi, ru, pl, sv, tr"


class TranslateTextInput(BaseModel):
    text: str = Field(description="Text to translate.")
    target_language: str = Field(description=f"Target language code (BCP-47). Examples: {_LANG_EXAMPLES}")
    source_language: str = Field(default="auto", description="Source language code, or 'auto' to detect automatically.")


class TranslateTextTool(BaseCallable):
    """Translate text to any target language using deep-translator (Google Translate backend)."""

    name = "translate_text"
    description = (
        "Translate text to a target language. "
        f"Accepts BCP-47 language codes: {_LANG_EXAMPLES}. "
        "Source language auto-detected by default. "
        "Returns the translated text."
    )
    callable_type = CallableType.TOOL
    input_schema = TranslateTextInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=20.0,
        requires_approval=False,
        network_allowed=True,
    )

    async def _execute(self, input: TranslateTextInput, context: CallContext) -> ToolOutput:
        try:
            from deep_translator import GoogleTranslator  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[translate_text: deep-translator not installed — run: pip install deep-translator]")

        if not input.text.strip():
            return ToolOutput(result="[translate_text: text is empty]")

        try:
            translator = GoogleTranslator(
                source=input.source_language,
                target=input.target_language,
            )
            # deep-translator has a 5000-char limit per call; chunk if needed
            text = input.text
            if len(text) <= 4900:
                translated = translator.translate(text)
            else:
                chunks = [text[i:i + 4900] for i in range(0, len(text), 4900)]
                translated = " ".join(translator.translate(chunk) for chunk in chunks)
        except Exception as exc:
            return ToolOutput(result=f"[translate_text: translation failed: {exc}]")

        src_label = input.source_language if input.source_language != "auto" else "auto-detected"
        return ToolOutput(
            result=f"[{src_label} → {input.target_language}]\n\n{translated}"
        )
