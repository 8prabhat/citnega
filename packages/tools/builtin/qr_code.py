"""qr_code — generate a QR code image from any text or URL."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class QRCodeInput(BaseModel):
    content: str = Field(description="Text or URL to encode in the QR code.")
    filename: str = Field(description="Output file path, e.g. ~/Desktop/qr.png")
    size: int = Field(default=300, description="Output image size in pixels (square).")
    error_correction: str = Field(
        default="M",
        description="Error correction level: L (7%) | M (15%) | Q (25%) | H (30%). Higher = more resilient but denser.",
    )
    border: int = Field(default=4, description="Quiet zone border width in modules.")


_ERROR_LEVELS = {"L", "M", "Q", "H"}


class QRCodeTool(BaseCallable):
    """Generate a QR code PNG image from any text or URL."""

    name = "qr_code"
    description = (
        "Generate a QR code image (PNG) from any text, URL, or structured data. "
        "Returns the path of the created image file."
    )
    callable_type = CallableType.TOOL
    input_schema = QRCodeInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=10.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: QRCodeInput, context: CallContext) -> ToolOutput:
        try:
            import qrcode  # type: ignore[import-untyped]
            from qrcode.constants import (  # type: ignore[import-untyped]
                ERROR_CORRECT_H,
                ERROR_CORRECT_L,
                ERROR_CORRECT_M,
                ERROR_CORRECT_Q,
            )
        except ImportError:
            return ToolOutput(result="[qr_code: qrcode not installed — run: pip install qrcode[pil]]")

        level_map = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
        ec = input.error_correction.upper()
        if ec not in _ERROR_LEVELS:
            return ToolOutput(result=f"[qr_code: invalid error_correction '{ec}'. Valid: L | M | Q | H]")

        out_path = Path(input.filename).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            qr = qrcode.QRCode(
                error_correction=level_map[ec],
                box_size=10,
                border=input.border,
            )
            qr.add_data(input.content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            # Resize to requested size
            img = img.resize((input.size, input.size))
            img.save(str(out_path))
        except Exception as exc:
            return ToolOutput(result=f"[qr_code: generation failed: {exc}]")

        return ToolOutput(
            result=f"QR code created: {out_path}  ({input.size}×{input.size}px, error_correction={ec})"
        )
