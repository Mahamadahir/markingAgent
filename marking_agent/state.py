import json
import sqlite3


AI_GENERATED = "AI_GENERATED"
APPROVED = "APPROVED"
OVERRIDDEN = "OVERRIDDEN"
FINAL_STATUSES = {APPROVED, OVERRIDDEN}


def connect_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS grading_records (
            student_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            provisional_ai_output TEXT NOT NULL,
            status TEXT NOT NULL,
            human_action TEXT,
            final_score TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (student_id, question_id)
        )
        """
    )
    connection.commit()


def get_record(connection, student_id, question_id):
    cursor = connection.execute(
        """
        SELECT * FROM grading_records
        WHERE student_id = ? AND question_id = ?
        """,
        (student_id, question_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def is_final_record(record):
    return bool(record and record["status"] in FINAL_STATUSES)


def save_provisional_evaluation(connection, student_id, question_id, evaluation, force=False):
    payload = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
    where_clause = "" if force else f"WHERE grading_records.status NOT IN ('{APPROVED}', '{OVERRIDDEN}')"
    connection.execute(
        f"""
        INSERT INTO grading_records (
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes
        ) VALUES (?, ?, ?, ?, NULL, NULL, NULL)
        ON CONFLICT(student_id, question_id) DO UPDATE SET
            provisional_ai_output = excluded.provisional_ai_output,
            status = excluded.status,
            human_action = NULL,
            final_score = NULL,
            notes = NULL,
            updated_at = CURRENT_TIMESTAMP
        {where_clause}
        """,
        (student_id, question_id, payload, AI_GENERATED),
    )
    connection.commit()


def save_human_decision(connection, student_id, question_id, evaluation, action, final_score, notes):
    if action not in FINAL_STATUSES:
        raise ValueError("Human action must be APPROVED or OVERRIDDEN.")

    payload = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
    connection.execute(
        """
        INSERT INTO grading_records (
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(student_id, question_id) DO UPDATE SET
            provisional_ai_output = excluded.provisional_ai_output,
            status = excluded.status,
            human_action = excluded.human_action,
            final_score = excluded.final_score,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (student_id, question_id, payload, action, action, final_score, notes),
    )
    connection.commit()


def evaluation_from_record(record):
    return json.loads(record["provisional_ai_output"])


def iter_records(connection, final_only=False):
    if final_only:
        cursor = connection.execute(
            """
            SELECT * FROM grading_records
            WHERE status IN (?, ?)
            ORDER BY student_id, question_id
            """,
            (APPROVED, OVERRIDDEN),
        )
    else:
        cursor = connection.execute(
            """
            SELECT * FROM grading_records
            ORDER BY student_id, question_id
            """
        )
    return [dict(row) for row in cursor.fetchall()]
