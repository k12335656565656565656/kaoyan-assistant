# Product Specification

## Product Positioning

The professional-course subject knowledge recognition module turns raw course material into a reviewable and user-curated knowledge base.

It is not positioned as a standalone OCR utility. OCR and text extraction are only the first stage of a broader learning workflow that ends with confirmed knowledge points suitable for later revision and reuse.

## Target Users

- MBA and postgraduate entrance exam candidates studying professional-course subjects
- Users who collect notes from PDFs, scanned pages, screenshots, and copied text
- Users who need structured review material instead of long uneditable summaries

## MVP Workflow

1. User enters material through one unified workspace.
2. System extracts text through the appropriate route.
3. System shows extracted text and asks the user to review or edit it.
4. User confirms the extracted text.
5. AI generates structured draft knowledge points in JSON.
6. User edits, deletes, or confirms each draft knowledge point.
7. System saves confirmed knowledge points to the user's private knowledge base.

## Unified Material Input Design

The MVP should use one unified material input area instead of separate pages for PDF, image, and pasted text.

Supported inputs:

- PDF upload
- Image upload
- Pasted text

Routing rules:

- Pasted text: clean and use directly
- Image: OCR
- PDF: try direct text extraction first
- PDF fallback: if extracted text is too short, low quality, or garbled, switch to OCR

Unified extraction result contract:

```json
{
  "source_type": "pdf | image | pasted_text",
  "process_method": "pdf_text_extract | pdf_ocr | image_ocr | pasted_text",
  "extracted_text": "...",
  "confidence": 0.0,
  "warnings": []
}
```

## Knowledge Point Confirmation Flow

Trust is a product requirement, not just a technical detail.

Rules:

- Do not start knowledge extraction before the user confirms the extracted text.
- Show extracted text in an editable form so the user can correct OCR mistakes or formatting issues.
- Generate draft knowledge points, not final truth claims.
- Preserve source evidence for each knowledge point using `source_text` and, where possible, source location metadata.
- Let the user edit, delete, or approve draft items individually before persistence.
- Save only confirmed knowledge points into the private knowledge base.

Suggested draft knowledge point fields:

- `knowledge_name`
- `knowledge_type`
- `subject`
- `chapter_name`
- `core_definition`
- `exam_question_styles`
- `keywords`
- `related_concepts`
- `pitfalls`
- `example_or_application`
- `review_priority`
- `source_text`
- `source_page`
- `source_location`
- `tags`
- `mastery_state`

## Future Features

- AI-generated explanations for saved knowledge points
- Exam question style generation from confirmed points
- Review cards and spaced-review workflows
- Follow-up AI expansion with explicit uncertainty labeling
- Better OCR confidence scoring and garbled-text detection
- Batch knowledge-point approval flows
- Knowledge deduplication and merge suggestions
- Search and filtering across the private knowledge base
