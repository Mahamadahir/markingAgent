# Marking Agent

A human-reviewed exam grading CLI and desktop prototype. It supports multiple exam projects, extracts the mark scheme to text, keeps handwritten exam papers as PDF references, sends each handwritten student response PDF as page images with the mark scheme text to an OpenAI model, saves provisional grading state in SQLite, and requires a human decision before final grades are exported.

## Status

This is a backend-first prototype for a future desktop UI. The command-line flow works, and the code is split so a UI can call the same grading, storage, PDF extraction, and state modules.

## Project Layout

```text
main.py                    # CLI entry point
marking_agent/
  cli.py                   # command-line workflow
  config.py                # default paths and CSV columns
  grading.py               # OpenAI call, schema, score validation
  mark_scheme.py           # question-specific mark scheme extraction
  pdf_extract.py           # selectable-text mark scheme PDF extraction
  state.py                 # SQLite state saving
  pdf_submissions.py       # handwritten PDF submission loading and page rendering
  storage.py               # text loading and CSV export
data/
  input/                   # local PDFs and source files
  extracted/               # extracted text files
  output/                  # SQLite state and CSV exports
```

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv markingAgent
source markingAgent/bin/activate
pip install -r requirements.txt
```

Set your OpenAI API key:

```bash
export OPENAI_API_KEY='your-key-here'
```

## Inputs

The grading command expects:

- a mark scheme text file
- a folder of student response PDFs

Put one handwritten script PDF per student in the submissions folder. The filename becomes the student ID:

```text
data/input/submissions/
  STUDENT_001.pdf
  STUDENT_002.pdf
  STUDENT_003.pdf
```

Each PDF is graded as a `FULL_SCRIPT` item against the mark scheme. The app rasterises the PDF pages locally and sends those page images to an image-capable OpenAI model.

Mark scheme headings should identify questions, for example:

```text
# Q1
Total: 2 marks
- 1 mark for ...

# Q2
Total: 3 marks
- 1 mark for ...
```

## Exam Projects

The SQLite database can hold multiple exams. Each grading record belongs to an `exam_id`, so students and question IDs from separate exams do not mix.

Create or reuse an exam by name when grading:

```bash
python main.py grade \
  --exam-name "Biology Paper 1" \
  --mark-scheme data/extracted/biology_paper_1_mark_scheme.txt \
  --submissions data/input/biology_paper_1_submissions \
  --output data/output/biology_paper_1.csv
```

List exams stored in the state database:

```bash
python main.py list-exams
```

Export one exam by ID, or all exams:

```bash
python main.py export-csv --exam-id biology-paper-1
python main.py export-csv --all-exams --output data/output/all_exams.csv
```

The desktop app has an exam name field on Project Setup. Loading a project creates or reuses that exam in SQLite.

## PDF Extraction

Only the mark scheme is converted to text:

```bash
python main.py extract-pdf data/input/mark_scheme.pdf data/extracted/mark_scheme.txt
```

Question papers and handwritten student responses stay as PDFs. Do not convert handwritten exam papers to text with this pipeline. The app turns each student response PDF page into an image and sends the page images to the grading model.

`pypdf` only extracts embedded text from selectable PDFs, so scanned mark schemes need OCR first. Student response PDFs do not need embedded text.

## Grading

Run the default grading flow:

```bash
python main.py grade
```

Run with explicit paths:

```bash
python main.py grade \
  --mark-scheme data/extracted/mark_scheme.txt \
  --submissions data/input/submissions \
  --db data/output/grading_state.sqlite3 \
  --output data/output/grading_output.csv
```

The model output is provisional. The CLI requires a human to approve or override every score before it becomes final.

### Question-Level Grading

The question IDs come from the mark scheme headings (`# Q1`, `Question 2`, and similar). Each student script is graded once per question, against that question's mark scheme snippet, and stored as a separate record. If the mark scheme has no question headings, the whole script is graded once as a single `FULL_SCRIPT` item.

To avoid sending every page to the model for every question, each script goes through one classification pass first: the page images and the question IDs are sent to the model, which labels each page with the questions answered on it. Grading a question then sends only that question's pages. Because the map is built per student from the actual script, it handles answers that overflow onto extra pages or run out of order. When the model is not confident about a page, or a question ends up with no pages assigned, grading falls back to sending the whole script for that question, so a bad map never silently grades a blank page.

The classification pass costs one extra model call per script, paid once and reused across that script's questions.

### Grading Providers

The grading call is behind a provider interface, so the same pipeline runs against OpenAI, Azure OpenAI, Anthropic (Claude), or Google (Gemini). Each provider translates the shared mark scheme text and page images into that backend's request format and returns the evaluation JSON. Adding a provider means implementing one `complete_json` method in `marking_agent/providers.py`.

Select a provider with `--provider` and pass the key with `--api-key`, or leave the key blank to use the provider's environment variable.

```bash
python main.py grade --provider openai --model gpt-4o
python main.py grade --provider anthropic --model claude-opus-4-8 --api-key sk-ant-...
python main.py grade --provider gemini --model gemini-1.5-pro --api-key ...
```

Each provider reads its own environment variable when `--api-key` is omitted: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, and `AZURE_OPENAI_API_KEY`.

For Azure OpenAI, `--model` is the deployment name:

```bash
export AZURE_OPENAI_API_KEY='your-key-here'
python main.py grade \
  --provider azure \
  --model my-gpt4o-deployment \
  --azure-endpoint https://my-resource.openai.azure.com \
  --azure-api-version 2024-08-01-preview
```

The provider, endpoint, and API version also read from `GRADING_PROVIDER`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_API_VERSION`.

In the desktop app, Project Setup has an LLM provider dropdown, a model/deployment field, an API key field, and the Azure endpoint fields (shown only when Azure is selected). The chosen provider and key are used for every AI evaluation in that session.

The provider and model are saved on the exam record (the API key is not), so reopening a project restores the backend it was last graded with. The dropdown and model field populate from the stored choice when a project loads.

## Desktop App

The desktop shell uses PySide6 and follows the `GradeAudit AI Assistant` Stitch project screens:

- Project Setup
- Extraction Review
- Grading Workspace
- Results

Run it from the activated virtual environment:

```bash
python -m marking_agent.desktop_app
```

The desktop app uses the same SQLite state database and CSV export path as the CLI. The exam name field scopes grading state to one exam project.

Build scripts are included for platform-specific packaging:

```bash
scripts/build_ubuntu.sh
scripts/build_macos.sh
```

Build on the target operating system. Use Ubuntu to produce the Linux build, and macOS to produce the `.app` bundle.

### Ubuntu Qt Dependencies

If the app fails with `Could not load the Qt platform plugin "xcb"`, install the missing Qt/XCB runtime packages:

```bash
sudo apt update
sudo apt install -y libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libgl1
```

Then run the app again:

```bash
python -m marking_agent.desktop_app
```

The packaged app uses the same system display libraries, so fix this before testing `dist/GradeAudit/GradeAudit`.

## State Saving

Runtime state is stored in SQLite:

```text
data/output/grading_state.sqlite3
```

The app saves provisional AI evaluations before asking for human approval. Records are scoped by exam project. If the process stops after the AI response but before approval, running the same command resumes from the saved provisional evaluation instead of calling the API again.

Final records are stored as:

- `APPROVED`
- `OVERRIDDEN`

CSV is an export format, not the primary state store.

## CSV Export

Export finalised records:

```bash
python main.py export-csv
```

With explicit paths:

```bash
python main.py export-csv \
  --db data/output/grading_state.sqlite3 \
  --output data/output/grading_output.csv
```

## Tests

Run tests:

```bash
python -m unittest
```

The tests cover question snippet extraction, PDF submission loading, image payload construction, score validation, SQLite state saving, resume protection, and CSV export.

## Development Notes

Local data, SQLite files, CSV exports, Python caches, and the virtual environment are ignored by git. Keep real exam data under `data/input`, `data/extracted`, or `data/output` so it stays local.
