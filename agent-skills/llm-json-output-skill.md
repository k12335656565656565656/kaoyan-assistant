# LLM JSON Output Skill

- The LLM should output valid JSON for knowledge extraction workflows.
- Avoid Markdown lists or prose-heavy output when the result is meant for machine parsing.
- Validate JSON structure before saving or rendering downstream.
- Add fallback behavior for invalid JSON, including retry or safe user-facing error handling.
- Required fields may be empty, but the output structure should remain stable.
