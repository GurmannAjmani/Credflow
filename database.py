import sqlite3
from datetime import datetime

DB_FILE = "credflow.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        name TEXT,
        email TEXT,
        password TEXT NOT NULL
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        run_id TEXT UNIQUE NOT NULL,
        raw_output_file TEXT,
        pdf_output_file TEXT,
        timestamp TEXT
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_runs_username ON runs(username)")
    c.execute("""
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        run_id TEXT NOT NULL,
        question TEXT,
        answer TEXT,
        citation TEXT
    )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_answers_runid ON answers(run_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_answers_username ON answers(username)")
    try:
        c.execute("ALTER TABLE runs ADD COLUMN pdf_output_file TEXT")
    except:
        pass

    conn.commit()
    conn.close()
def create_user(username, name, email, password):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    INSERT INTO users (username, name, email, password)
    VALUES (?, ?, ?, ?)
    """, (username, name, email, password))

    conn.commit()
    conn.close()


def get_user(username):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    conn.close()
    return user
def save_run(username, run_id, raw_output_file, pdf_output_file=None):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    INSERT INTO runs (username, run_id, raw_output_file, pdf_output_file, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (
        username,
        run_id,
        raw_output_file,
        pdf_output_file,
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()


def update_run_pdf(run_id, pdf_output_file):
    """Update a run with the generated PDF file path."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    UPDATE runs
    SET pdf_output_file = ?
    WHERE run_id = ?
    """, (pdf_output_file, run_id))

    conn.commit()
    conn.close()
def save_answers(username, run_id, output_json):
    conn = get_connection()
    c = conn.cursor()

    for item in output_json:
        c.execute("""
        INSERT INTO answers
        (username, run_id, question, answer, citation)
        VALUES (?, ?, ?, ?, ?)
        """, (
            username,
            run_id,
            item.get("question"),
            item.get("answer"),
            item.get("citation")
        ))

    conn.commit()
    conn.close()


def get_user_history(username):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    SELECT run_id, raw_output_file, pdf_output_file, timestamp
    FROM runs
    WHERE username = ?
    ORDER BY timestamp DESC
    LIMIT 10
    """, (username,))

    rows = c.fetchall()
    conn.close()
    return rows