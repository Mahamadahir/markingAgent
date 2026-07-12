# Blueprint: Multi-Agent Exam Grading CLI Application

## 1. System Architecture Overview
This application uses a multi-agent workflow to orchestrate, evaluate, and record exam grading with a mandatory human-in-the-loop validation barrier.

```text
+--------------------------------------------------------------+
|                    Agent 1: Orchestrator                     |
|  - Loads exam papers & mark scheme                           |
|  - Tracks global state loop (Student -> Question)            |
|  - Prepares isolated payloads per question                   |
+------------------------------+-------------------------------+
                               |
                               | (Question + Answer + Mark Scheme Snippet)
                               v
+------------------------------+-------------------------------+
|                 Agent 2: Grading Assistant                   |
|  - Compares text strictly to Mark Scheme                     |
|  - Flags deviations [DEVIATION DETECTED]                     |
|  - Generates provisional breakdown and score                 |
+------------------------------+-------------------------------+
                               |
                               | (Provisional Evaluation)
                               v
+------------------------------+-------------------------------+
|                 [HUMAN-IN-THE-LOOP BARRIER]                  |
|  - CLI pauses entirely                                       |
|  - Human inputs: APPROVE or OVERRIDE [Score] [Reason]        |
+------------------------------+-------------------------------+
                               |
                               | (Validated Decision)
                               v
+------------------------------+-------------------------------+
|             State Update & Incremental Storage               |
|  - Agent 1 appends verified results to internal state        |
|  - Flushes data safely to grading_output.csv                 |
+--------------------------------------------------------------+
```

## 2. File and Data Specifications

### Input 1: `mark_scheme.txt` (Plain Text)
Contains the definitive, comprehensive marking criteria structured by question identifiers.

### Input 2: `students_exams.json` (Structured JSON)
```json
[
  {
    "student_id": "STUDENT_001",
    "exam_responses": {
      "Q1": "The student response text for question one...",
      "Q2": "The student response text for question two..."
    }
  }
]
```

### Output: `grading_output.csv` (Flat Matrix Data)
The file must write incrementally after *every single user confirmation* using standard UTF-8 encoding.
Columns: `Student ID`, `Question ID`, `Provisional AI Output`, `Human Action`, `Final Score`, `Notes`

## 3. Agent Prompts

### Agent 1: Orchestrator System Prompt
```text
You are the central data orchestrator for an exam grading workflow. Your responsibility is to ingest the complete repository of student exam submissions, manage the sequential distribution of individual questions to the Grading Agent, handle human verification loops, and compile the final grades into a structured format suitable for a spreadsheet.

Core Directives:
1. Context Management: Maintain the global state of the grading process (Student IDs, Questions, Final Marks, and Flagged Deviations).
2. Sequential Dispatch: Extract exactly one student's answer for one specific question at a time. Dispatch this raw text along with the relevant section of the official mark scheme to the Grading Agent.
3. State Suspension: After dispatching a question, wait for the Grading Agent's evaluation and subsequent human verification. Do not proceed to the next question or student until the current evaluation is finalized.
4. Data Compilation: Map the validated marks and any deviation flags to the respective student record. Once all questions for all students are processed, output the comprehensive dataset as a clean markdown table ready for spreadsheet export.
```

### Agent 2: Grading & Deviation Agent System Prompt
```text
You are a precise, objective academic grading assistant. Your sole purpose is to evaluate a single student response against the provided mark scheme snippet for that specific question. You operate in an isolated environment per execution and must never assume context outside of the current payload.

Core Directives:
1. Single Source of Truth: Evaluate the student response strictly against the provided mark scheme snippet. Do not award marks for external knowledge or alternative correct answers unless the mark scheme explicitly permits it.
2. Deviation Flagging: If the student's answer contains assertions, methodologies, or terminology that deviate from or contradict the mark scheme, you must flag it immediately.
3. Human-in-the-Loop Interlock: Your evaluation is a provisional proposal. You must explicitly halt the process and request human review before releasing the data back to Agent 1.

Output Formatting:
You must structure your response exactly as follows to facilitate human review:

## PROVISIONAL EVALUATION: [Question ID] (Student: [Student ID])

### 1. Deviation Assessment
[DEVIATION DETECTED: YES/NO]
*If YES, detail exactly where the student response diverged from the official criteria.*

### 2. Proposed Marks
- Total Marks Available: [X]
- Proposed Marks Awarded: [Y]

### 3. Criteria Breakdown
- [Criteria Point 1]: [Awarded/Not Awarded] – [Evidence from student text]
- [Criteria Point 2]: [Awarded/Not Awarded] – [Evidence from student text]
```

## 4. Complete Executable Implementation (Python)

```python
import os
import json
import csv
import sys
import re
from openai import OpenAI

# Initialize the OpenAI Client - falls back to environment variable OPENAI_API_KEY
client = OpenAI()

# Model selection configuration
MODEL_NAME = "gpt-4o" 

# Inlined Agent Prompts from Section 3
ORCHESTRATOR_PROMPT = """You are the central data orchestrator for an exam grading workflow. Your responsibility is to ingest the complete repository of student exam submissions, manage the sequential distribution of individual questions to the Grading Agent, handle human verification loops, and compile the final grades into a structured format suitable for a spreadsheet."""

GRADER_PROMPT = """You are a precise, objective academic grading assistant. Your sole purpose is to evaluate a single student response against the provided mark scheme snippet for that specific question. You operate in an isolated environment per execution and must never assume context outside of the current payload.

Core Directives:
1. Single Source of Truth: Evaluate the student response strictly against the provided mark scheme snippet. Do not award marks for external knowledge or alternative correct answers unless the mark scheme explicitly permits it.
2. Deviation Flagging: If the student's answer contains assertions, methodologies, or terminology that deviate from or contradict the mark scheme, you must flag it immediately.
3. Human-in-the-Loop Interlock: Your evaluation is a provisional proposal. You must explicitly halt the process and request human review before releasing the data back to Agent 1.

Output Formatting:
You must structure your response exactly as follows to facilitate human review:

## PROVISIONAL EVALUATION: [Question ID] (Student: [Student ID])

### 1. Deviation Assessment
[DEVIATION DETECTED: YES/NO]
*If YES, detail exactly where the student response diverged from the official criteria.*

### 2. Proposed Marks
- Total Marks Available: [X]
- Proposed Marks Awarded: [Y]

### 3. Criteria Breakdown
- [Criteria Point 1]: [Awarded/Not Awarded] – [Evidence from student text]
- [Criteria Point 2]: [Awarded/Not Awarded] – [Evidence from student text]"""

def load_source_data():
    """Validates and loads local marking asset structures."""
    if not os.path.exists("mark_scheme.txt"):
        print("Error: 'mark_scheme.txt' missing from root directory.")
        sys.exit(1)
        
    if not os.path.exists("students_exams.json"):
        print("Error: 'students_exams.json' missing from root directory.")
        sys.exit(1)

    with open("mark_scheme.txt", "r", encoding="utf-8") as f:
        mark_scheme = f.read()

    with open("students_exams.json", "r", encoding="utf-8") as f:
        student_data = json.load(f)

    return mark_scheme, student_data

def call_grading_agent(student_id, question_id, student_answer, full_mark_scheme):
    """Executes isolated LLM grading context payload execution."""
    dispatch_payload = f"""### GRADED DISPATCH REQUEST ###
- Student ID: {student_id}
- Question ID: {question_id}
---
MARK SCHEME REFERENCE DATA:
{full_mark_scheme}
---
RAW STUDENT RESPONSE FOR EVALUATION:
{student_answer}"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": GRADER_PROMPT},
                {"role": "user", "content": dispatch_payload}
            ],
            temperature=0.0 # Force absolute determinism 
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"\nAPI Error encountered during evaluation: {e}")
        sys.exit(1)

def append_to_csv(row_data, file_path="grading_output.csv"):
    """Writes transactional evaluations safely to permanent disk storage."""
    file_exists = os.path.exists(file_path)
    fieldnames = ["Student ID", "Question ID", "Provisional AI Output", "Human Action", "Final Score", "Notes"]
    
    with open(file_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_data)

def parse_proposed_score(ai_text):
    """Attempts helper parsing to pre-fill prompts for human optimization."""
    match = re.search(r"Proposed Marks Awarded:\s*\[?(\d+)\]?", ai_text, re.IGNORECASE)
    return match.group(1) if match else ""

def main():
    print("Initializing Multi-Agent Grading Environment...")
    mark_scheme, student_data = load_source_data()
    
    # Execution Loop
    for student_entry in student_data:
        student_id = student_entry.get("student_id")
        responses = student_entry.get("exam_responses", {})
        
        for q_id, s_answer in responses.items():
            print(f"\n\n{'='*60}")
            print(f"RUNNING EVALUATION: {student_id} | {q_id}")
            print(f"{'='*60}\n")
            
            # Step 1: Agent 1 calls Agent 2
            print("Orchestrator pulling token window... Awaiting Grading Agent analysis...")
            ai_evaluation = call_grading_agent(student_id, q_id, s_answer, mark_scheme)
            
            # Step 2: Render Evaluation for Human Verification Barrier
            print("\n" + ai_evaluation + "\n")
            print("-" * 60)
            
            # Extract basic score indicator for CLI entry pre-fill guidance
            suggested_score = parse_proposed_score(ai_evaluation)
            hint_str = f" [Suggested: {suggested_score}]" if suggested_score else ""
            
            # Step 3: Human Action Loop Interlock
            while True:
                action_input = input("Enter decision ('APPROVE' or 'OVERRIDE'): ").strip().upper()
                if action_input in ["APPROVE", "OVERRIDE"]:
                    break
                print("Invalid instruction string. Match required syntax parameters precisely.")

            final_score = ""
            notes = ""
            
            if action_input == "APPROVE":
                final_score = input(f"Confirm numeric score value to log{hint_str}: ").strip()
                notes = "Approved AI assessment values without manual variant edits."
            else:
                final_score = input("Input custom overridden numeric score: ").strip()
                notes = input("Provide descriptive mandatory audit reason for override sequence: ").strip()

            # Step 4: Record output row to disk via transactional CSV update
            record = {
                "Student ID": student_id,
                "Question ID": q_id,
                "Provisional AI Output": ai_evaluation,
                "Human Action": action_input,
                "Final Score": final_score,
                "Notes": notes
            }
            append_to_csv(record)
            print(f"Transaction recorded successfully for {student_id} - {q_id}.")

    print("\n\nAll exam arrays cleared completely. Spreadsheet generation phase locked down.")

if __name__ == "__main__":
    main()
```
