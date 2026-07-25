# Professional Knowledge Assets

The public repository contains the code, generators, validation rules, and
structure-only true-exam archetypes. It does not version local course notes or
generated catalogs derived from material whose redistribution rights may be
restricted.

To enable the full 313 history catalog:

1. Build or obtain an authorized `builtin_history_points.json`.
2. Keep it outside Git, or place it at
   `professional_knowledge/builtin_history_points.json` (ignored by default).
3. For private deployments, set `HISTORY_KNOWLEDGE_CATALOG` to the catalog's
   absolute or deployment-relative path.

The application remains usable without this optional asset; user-provided
materials can still populate the history knowledge base.
