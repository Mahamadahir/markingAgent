# Tasks

## Done
- Provider interface for grading (OpenAI, Azure OpenAI, Anthropic/Claude, Google/Gemini) with in-app LLM selection and API key entry.
- Question-level grading: each script graded per mark scheme question, with a `FULL_SCRIPT` fallback when the scheme has no question headings.
- CI/CD: test workflow and rolling release build.
- Per-module test suite.
- CSV export: `export-csv` CLI command (`--exam-id` / `--all-exams`) and the Results screen Export CSV button, plus auto-export after each human decision.
- Page-to-question mapping: a per-script classification pass labels each page with the questions answered on it, so grading a question sends only its pages, with a whole-script fallback when the map is uncertain.
- Persist provider and model per exam (not the API key). Saved on the exam record and restored into the desktop dropdown when a project loads.
- OCR for scanned mark schemes. Extraction has a per-run mode (never / auto / always) using Tesseract; auto runs OCR only on pages with no embedded text.

## Next
1. Verify Claude and Gemini against live APIs. Both paths are correct by construction but unproven; Gemini relies on prompt-injected schema rather than native enforcement, so it is the most likely to return malformed JSON. This now also covers the page classification pass.
2. Retries, rate-limit handling, and token/cost logging on the API call.
