from dataclasses import asdict, dataclass, field
from typing import List, Literal

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
