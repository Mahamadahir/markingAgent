import json
import sqlite3
import uuid


AI_GENERATED = "AI_GENERATED"
APPROVED = "APPROVED"
OVERRIDDEN = "OVERRIDDEN"
FINAL_STATUSES = {APPROVED, OVERRIDDEN}
DEFAULT_EXAM_ID = "default"
DEFAULT_EXAM_NAME = "Default Exam"


def connect_database(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialise_database(connection):
    create_exams_table(connection)
    ensure_exam_columns(connection)
    ensure_default_exam(connection)
    ensure_grading_records_table(connection)
    connection.commit()


def create_exams_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS exams (
            exam_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            subject TEXT,
            paper TEXT,
            exam_date TEXT,
            mark_scheme_path TEXT,
            question_paper_path TEXT,
            students_path TEXT,
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_exam_columns(connection):
    columns = table_columns(connection, "exams")
    for column in ("provider", "model"):
        if column not in columns:
            connection.execute(f"ALTER TABLE exams ADD COLUMN {column} TEXT DEFAULT ''")


def ensure_default_exam(connection):
    connection.execute(
        """
        INSERT OR IGNORE INTO exams (exam_id, name)
        VALUES (?, ?)
        """,
        (DEFAULT_EXAM_ID, DEFAULT_EXAM_NAME),
    )


def ensure_grading_records_table(connection):
    if not table_exists(connection, "grading_records"):
        create_grading_records_table(connection)
        return

    columns = table_columns(connection, "grading_records")
    if "exam_id" in columns:
        return

    connection.execute("ALTER TABLE grading_records RENAME TO grading_records_legacy")
    create_grading_records_table(connection)
    connection.execute(
        """
        INSERT INTO grading_records (
            exam_id,
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes,
            created_at,
            updated_at
        )
        SELECT
            ?,
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes,
            created_at,
            updated_at
        FROM grading_records_legacy
        """,
        (DEFAULT_EXAM_ID,),
    )
    connection.execute("DROP TABLE grading_records_legacy")


def create_grading_records_table(connection):
    connection.execute(
        """
        CREATE TABLE grading_records (
            exam_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            question_id TEXT NOT NULL,
            provisional_ai_output TEXT NOT NULL,
            status TEXT NOT NULL,
            human_action TEXT,
            final_score TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (exam_id, student_id, question_id),
            FOREIGN KEY (exam_id) REFERENCES exams(exam_id)
        )
        """
    )


def table_exists(connection, table_name):
    cursor = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    )
    return cursor.fetchone() is not None


def table_columns(connection, table_name):
    cursor = connection.execute(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in cursor.fetchall()}


def create_exam(
    connection,
    name,
    subject="",
    paper="",
    exam_date="",
    mark_scheme_path="",
    question_paper_path="",
    students_path="",
    provider="",
    model="",
    exam_id=None,
):
    exam_id = exam_id or uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO exams (
            exam_id,
            name,
            subject,
            paper,
            exam_date,
            mark_scheme_path,
            question_paper_path,
            students_path,
            provider,
            model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exam_id) DO UPDATE SET
            name = excluded.name,
            subject = excluded.subject,
            paper = excluded.paper,
            exam_date = excluded.exam_date,
            mark_scheme_path = excluded.mark_scheme_path,
            question_paper_path = excluded.question_paper_path,
            students_path = excluded.students_path,
            provider = excluded.provider,
            model = excluded.model,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            exam_id,
            name,
            subject,
            paper,
            exam_date,
            mark_scheme_path,
            question_paper_path,
            students_path,
            provider,
            model,
        ),
    )
    connection.commit()
    return exam_id


def set_exam_provider(connection, exam_id, provider, model):
    connection.execute(
        """
        UPDATE exams
        SET provider = ?, model = ?, updated_at = CURRENT_TIMESTAMP
        WHERE exam_id = ?
        """,
        (provider, model, exam_id),
    )
    connection.commit()


def get_exam(connection, exam_id):
    cursor = connection.execute(
        """
        SELECT * FROM exams
        WHERE exam_id = ?
        """,
        (exam_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_exam_by_name(connection, name):
    cursor = connection.execute(
        """
        SELECT * FROM exams
        WHERE name = ?
        ORDER BY created_at
        LIMIT 1
        """,
        (name,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def list_exams(connection):
    cursor = connection.execute(
        """
        SELECT * FROM exams
        ORDER BY updated_at DESC, name ASC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def ensure_exam(connection, exam_id=None, name=None, **metadata):
    if exam_id:
        existing = get_exam(connection, exam_id)
        if existing:
            return exam_id
        return create_exam(connection, name or exam_id, exam_id=exam_id, **metadata)

    if name:
        existing = get_exam_by_name(connection, name)
        if existing:
            return existing["exam_id"]
        return create_exam(connection, name, **metadata)

    ensure_default_exam(connection)
    connection.commit()
    return DEFAULT_EXAM_ID


def get_record(connection, exam_id, student_id, question_id):
    cursor = connection.execute(
        """
        SELECT * FROM grading_records
        WHERE exam_id = ? AND student_id = ? AND question_id = ?
        """,
        (exam_id, student_id, question_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def is_final_record(record):
    return bool(record and record["status"] in FINAL_STATUSES)


def save_provisional_evaluation(connection, exam_id, student_id, question_id, evaluation, force=False):
    payload = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
    where_clause = "" if force else f"WHERE grading_records.status NOT IN ('{APPROVED}', '{OVERRIDDEN}')"
    connection.execute(
        f"""
        INSERT INTO grading_records (
            exam_id,
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
        ON CONFLICT(exam_id, student_id, question_id) DO UPDATE SET
            provisional_ai_output = excluded.provisional_ai_output,
            status = excluded.status,
            human_action = NULL,
            final_score = NULL,
            notes = NULL,
            updated_at = CURRENT_TIMESTAMP
        {where_clause}
        """,
        (exam_id, student_id, question_id, payload, AI_GENERATED),
    )
    connection.commit()


def save_human_decision(connection, exam_id, student_id, question_id, evaluation, action, final_score, notes):
    if action not in FINAL_STATUSES:
        raise ValueError("Human action must be APPROVED or OVERRIDDEN.")

    payload = json.dumps(evaluation, ensure_ascii=False, sort_keys=True)
    connection.execute(
        """
        INSERT INTO grading_records (
            exam_id,
            student_id,
            question_id,
            provisional_ai_output,
            status,
            human_action,
            final_score,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(exam_id, student_id, question_id) DO UPDATE SET
            provisional_ai_output = excluded.provisional_ai_output,
            status = excluded.status,
            human_action = excluded.human_action,
            final_score = excluded.final_score,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (exam_id, student_id, question_id, payload, action, action, final_score, notes),
    )
    connection.commit()


def evaluation_from_record(record):
    return json.loads(record["provisional_ai_output"])


def iter_records(connection, exam_id=None, final_only=False):
    filters = []
    params = []
    if exam_id:
        filters.append("grading_records.exam_id = ?")
        params.append(exam_id)
    if final_only:
        filters.append("grading_records.status IN (?, ?)")
        params.extend([APPROVED, OVERRIDDEN])

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    cursor = connection.execute(
        f"""
        SELECT grading_records.*, exams.name AS exam_name
        FROM grading_records
        LEFT JOIN exams ON exams.exam_id = grading_records.exam_id
        {where_clause}
        ORDER BY exams.name, grading_records.student_id, grading_records.question_id
        """,
        params,
    )
    return [dict(row) for row in cursor.fetchall()]
