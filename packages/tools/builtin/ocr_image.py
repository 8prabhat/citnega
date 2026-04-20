"""ocr_image — extract text from an image or PDF page using pytesseract / pdfplumber."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
_PDF_SUFFIX = ".pdf"


class OCRImageInput(BaseModel):
    image_path: str = Field(description="Path to an image file (PNG/JPG/BMP/TIFF) or PDF.")
    language: str = Field(default="eng", description="Tesseract language code, e.g. 'eng', 'fra', 'deu', 'chi_sim'.")
    pdf_page: int = Field(default=1, description="Page number to extract from PDF (1-based). Ignored for images.")
    psm: int = Field(default=3, description="Tesseract page segmentation mode (0–13). Default 3 = auto.")


class OCRImageTool(BaseCallable):
    """
    Extract text from an image (PNG/JPG/BMP/TIFF) or PDF page.

    Uses pytesseract for images (requires Tesseract installed on the system).
    Falls back to pdfplumber for PDFs (pure Python, no system dependency).
    """

    name = "ocr_image"
    description = (
        "Extract text from an image file (PNG, JPG, BMP, TIFF) using OCR (pytesseract). "
        "For PDF files, extracts text layer directly via pdfplumber (no OCR needed for digital PDFs). "
        "Returns the extracted text. Requires Tesseract to be installed for image OCR."
    )
    callable_type = CallableType.TOOL
    input_schema = OCRImageInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: OCRImageInput, context: CallContext) -> ToolOutput:
        path = Path(input.image_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[ocr_image: file not found: {path}]")

        suffix = path.suffix.lower()

        # PDF path — try pdfplumber first (no system dep)
        if suffix == _PDF_SUFFIX:
            return await self._extract_pdf(path, input.pdf_page)

        # Image path — use pytesseract
        if suffix not in _IMAGE_SUFFIXES:
            return ToolOutput(result=f"[ocr_image: unsupported file type '{suffix}'. Supported: {', '.join(sorted(_IMAGE_SUFFIXES | {_PDF_SUFFIX}))}]")

        return await self._extract_image(path, input.language, input.psm)

    @staticmethod
    async def _extract_pdf(path: Path, page_num: int) -> ToolOutput:
        try:
            import pdfplumber  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[ocr_image: pdfplumber not installed — run: pip install pdfplumber]")

        try:
            with pdfplumber.open(str(path)) as pdf:
                if page_num < 1 or page_num > len(pdf.pages):
                    return ToolOutput(result=f"[ocr_image: PDF has {len(pdf.pages)} page(s); requested page {page_num}]")
                page = pdf.pages[page_num - 1]
                text = page.extract_text() or ""
        except Exception as exc:
            return ToolOutput(result=f"[ocr_image: PDF extraction failed: {exc}]")

        if not text.strip():
            return ToolOutput(result=f"[ocr_image: no text layer found on page {page_num}. This may be a scanned PDF — use an image-based OCR workflow.]")

        return ToolOutput(result=f"PDF: {path.name} (page {page_num})\n\n{text}")

    @staticmethod
    async def _extract_image(path: Path, language: str, psm: int) -> ToolOutput:
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
        except ImportError as e:
            missing = "pytesseract" if "pytesseract" in str(e) else "Pillow"
            return ToolOutput(result=f"[ocr_image: {missing} not installed — run: pip install pytesseract Pillow]")

        try:
            img = Image.open(str(path))
            config = f"--psm {psm}"
            text = pytesseract.image_to_string(img, lang=language, config=config)
        except pytesseract.TesseractNotFoundError:
            return ToolOutput(result="[ocr_image: Tesseract not found. Install it: brew install tesseract (macOS) or apt install tesseract-ocr (Linux)]")
        except Exception as exc:
            return ToolOutput(result=f"[ocr_image: OCR failed: {exc}]")

        if not text.strip():
            return ToolOutput(result=f"[ocr_image: no text detected in {path.name}. Try a higher resolution image or different PSM mode.]")

        return ToolOutput(result=f"OCR: {path.name}\n\n{text}")
