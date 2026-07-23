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
- Model listing per provider: query the provider API with the entered key to populate the model dropdown (CLI `list-models`, desktop Fetch models button); Azure lists deployments so is entered manually.
- Multi-model consensus: grade an item against several models (works with one key via different models from the same provider) and flag disagreements, which sort to the top of the review queue alongside low-confidence items.
- Topic labelling per question: a model pass over the mark scheme returns a topic per question ID, stored against the exam (CLI `extract-topics`, desktop Label Topics button) and exported as a CSV Topic column.

## Next
1. Verify Claude and Gemini against live APIs. Both paths are correct by construction but unproven; Gemini relies on prompt-injected schema rather than native enforcement, so it is the most likely to return malformed JSON. This now also covers the page classification pass.
2. Retries, rate-limit handling, and token/cost logging on the API call.

## Backlog

### Trust and grading quality
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
- Roster mapping: map filenames to real student names from an imported roster. Prerequisite for cross-exam student history.
- Anonymised marking: strip or redact names before grading, re-attach after.

Note: the input items and any LMS integration are only worth building if the real workflow hits them. Do not build speculatively.

### Topics and history (exploring)
- History-aware feedback sheets: generate per-student feedback from the student's stored structured records across all exams (finalised marks, topic tags, criteria breakdown, notes), not the raw scripts. The raw scripts never leave the grading step. Sourcing from the records is the data-minimising, cheaper (text not images), cross-exam-by-query version. Needs persistent student identity (roster mapping) and benefits from topic labelling. Data-protection note: even the structured history is sensitive personal data — decide provider/retention deliberately (see Azure OpenAI below).

## Final potential steps (institutional / multi-user)

A product pivot: these turn the local single-user tool into a shared institutional service. Do not build piecemeal onto the desktop app; confirm the product direction before starting any of this.

- PostgreSQL as a database option. The hinge for multi-user. Introduce a data-access layer (SQLAlchemy Core or a repository interface) once, targeting SQLite (local) or Postgres (shared) via a connection URL, rather than hand-porting the raw SQL in `state.py` to two dialects.
- Multi-user with departments. Organisation → department → user model, exams scoped to a department, roles (marker, moderator, admin), per-department usage tracking and quotas. Needs Postgres and auth (likely institution SSO).
- Server-side single API key. For an institutional shared key the key must move server-side and every model call be brokered by a backend — never distributed to desktop clients. This effectively requires growing a server, with the desktop or a web client as a thin authenticated front-end.
- Azure OpenAI as the recommended provider for an institutional deployment and for history-based feedback: model runs in the institution's own Azure tenant, not used for training, region-pinned for UK/EU residency, enterprise DPA, and optional zero data retention (apply for the modified abuse-monitoring exemption). Still requires a DPIA and lawful basis — Azure makes the paperwork passable, not unnecessary.
