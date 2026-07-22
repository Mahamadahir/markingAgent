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
- Confidence flagging: each grade carries a model confidence; low-confidence provisional items sort to the top of the desktop review queue and are flagged, and confidence is included in the CSV export.

## Next
1. Verify Claude and Gemini against live APIs. Both paths are correct by construction but unproven; Gemini relies on prompt-injected schema rather than native enforcement, so it is the most likely to return malformed JSON. This now also covers the page classification pass.
2. Retries, rate-limit handling, and token/cost logging on the API call.

## Backlog

### Trust and grading quality
- Multi-model consensus: grade each item with two providers and flag disagreements for human review.
- Rubric calibration pass: grade teacher-marked sample scripts first, show divergence, tune the scheme before the full run.
- Re-grade a single item from the desktop (different model or edited scheme) instead of `--no-resume` for the whole run.

### Speed and workflow
- Concurrent grading. Grading is sequential today; batch or parallelise once retries and rate-limit handling land.
- Cost/token estimate before a run (images and questions counted, approximate cost and call count shown).
- Results table filtering, search, and bulk approve for large cohorts.

### Outputs
- Per-student feedback sheets (marks, per-criterion breakdown, deviation notes) as PDF or markdown.
- Cohort analytics: mark distribution per question, hardest questions, per-student totals.
- Excel export alongside CSV.

### Inputs
- Multi-student single PDF splitting (one scanned batch file into per-student scripts).
- Roster mapping: map filenames to real student names from an imported roster.
- Anonymised marking: strip or redact names before grading, re-attach after.

Note: the input items and any LMS integration are only worth building if the real workflow hits them. Do not build speculatively.
