# Marking Agent

A human-reviewed exam grading CLI. It extracts text from PDFs, sends one student answer and one mark-scheme snippet to an OpenAI model, saves provisional grading state in SQLite, and requires a human decision before final grades are exported.

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
  pdf_extract.py           # selectable-text PDF extraction
  state.py                 # SQLite state saving
  storage.py               # JSON loading and CSV export
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
- a student responses JSON file

Example `students_exams.json`:

```json
[
  {
    "student_id": "STUDENT_001",
    "exam_responses": {
      "Q1": "Student answer text...",
      "Q2": "Student answer text..."
    }
  }
]
```

Mark scheme headings should identify questions, for example:

```text
# Q1
Total: 2 marks
- 1 mark for ...

# Q2
Total: 3 marks
- 1 mark for ...
```

## PDF Extraction

For selectable-text PDFs:

```bash
python main.py extract-pdf data/input/mark_scheme.pdf data/extracted/mark_scheme.txt
python main.py extract-pdf data/input/question_paper.pdf data/extracted/question_paper.txt
```

Scanned PDFs need OCR or vision extraction before grading. `pypdf` only extracts embedded text.

## Grading

Run the default grading flow:

```bash
python main.py grade
```

Run with explicit paths:

```bash
python main.py grade \
  --mark-scheme data/extracted/mark_scheme.txt \
  --students students_exams.json \
  --db data/output/grading_state.sqlite3 \
  --output data/output/grading_output.csv
```

The model output is provisional. The CLI requires a human to approve or override every score before it becomes final.

## State Saving

Runtime state is stored in SQLite:

```text
data/output/grading_state.sqlite3
```

The app saves provisional AI evaluations before asking for human approval. If the process stops after the AI response but before approval, running the same command resumes from the saved provisional evaluation instead of calling the API again.

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

The tests cover question snippet extraction, score validation, SQLite state saving, resume protection, and CSV export.

## Development Notes

Local data, SQLite files, CSV exports, Python caches, and the virtual environment are ignored by git. Keep real exam data under `data/input`, `data/extracted`, or `data/output` so it stays local.
