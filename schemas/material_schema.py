from dataclasses import asdict, dataclass, field, fields
from typing import Any, List, Literal

SourceType = Literal["pdf", "image", "pasted_text"]
ProcessMethod = Literal["pdf_text_extract", "pdf_ocr", "image_ocr", "pasted_text"]


@dataclass
class MaterialResult:
    source_type: SourceType
    process_method: ProcessMethod
    extracted_text: str
    confidence: float
    warnings: List[str] = field(default_factory=list)
    raw_extracted_text: str = ""
    page_count: int = 0
    empty_page_count: int = 0
    pdf_diagnostics: dict = field(default_factory=dict)
    ocr_report: dict = field(default_factory=dict)
    clean_report: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Any) -> "MaterialResult":
        """Build a result from persisted JSON while tolerating older/newer rows."""
        if not isinstance(payload, dict):
            payload = {}
        allowed = {item.name for item in fields(cls)}
        values = {key: value for key, value in payload.items() if key in allowed}
        if values.get("source_type") not in {"pdf", "image", "pasted_text"}:
            values["source_type"] = "pasted_text"
        if values.get("process_method") not in {
            "pdf_text_extract",
            "pdf_ocr",
            "image_ocr",
            "pasted_text",
        }:
            values["process_method"] = "pasted_text"
        for key in ("extracted_text", "raw_extracted_text"):
            values[key] = str(values.get(key) or "")
        try:
            values["confidence"] = min(1.0, max(0.0, float(values.get("confidence", 0.0))))
        except (TypeError, ValueError):
            values["confidence"] = 0.0
        warnings = values.get("warnings")
        if not isinstance(warnings, list):
            warnings = [warnings] if warnings else []
        values["warnings"] = [str(item) for item in warnings if item is not None]
        for key in ("page_count", "empty_page_count"):
            try:
                values[key] = max(0, int(values.get(key, 0) or 0))
            except (TypeError, ValueError):
                values[key] = 0
        for key in ("pdf_diagnostics", "ocr_report", "clean_report"):
            if not isinstance(values.get(key), dict):
                values[key] = {}
        return cls(**values)
