from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import json
import mimetypes
import sqlite3
from datetime import date, timedelta


ROOT = Path(__file__).parent
DB_PATH = ROOT / "pulsehabits.db"
PUBLIC = ROOT / "public"


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with connect() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                weekly_goal INTEGER NOT NULL DEFAULT 5,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                completed_on TEXT NOT NULL,
                UNIQUE(habit_id, completed_on),
                FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE
            )
            """
        )
        count = db.execute("SELECT COUNT(*) AS total FROM habits").fetchone()["total"]
        if count == 0:
            today = date.today().isoformat()
            db.executemany(
                "INSERT INTO habits (name, category, weekly_goal, created_at) VALUES (?, ?, ?, ?)",
                [
                    ("Estudar 40 minutos", "Estudos", 5, today),
                    ("Treinar ou caminhar", "Saude", 4, today),
                    ("Ler 10 paginas", "Foco", 5, today),
                ],
            )


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def week_start(day):
    return day - timedelta(days=day.weekday())


def get_habits():
    today = date.today()
    start = week_start(today)
    end = start + timedelta(days=6)

    with connect() as db:
        habits = [row_to_dict(row) for row in db.execute("SELECT * FROM habits ORDER BY id DESC")]
        completions = db.execute(
            """
            SELECT habit_id, completed_on
            FROM completions
            WHERE completed_on BETWEEN ? AND ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()

    completed_by_habit = {}
    for item in completions:
        completed_by_habit.setdefault(item["habit_id"], set()).add(item["completed_on"])

    for habit in habits:
        dates = completed_by_habit.get(habit["id"], set())
        habit["completed_today"] = today.isoformat() in dates
        habit["week_count"] = len(dates)
        habit["progress"] = min(100, round((len(dates) / habit["weekly_goal"]) * 100))

    return habits


def create_habit(payload):
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "Geral")).strip() or "Geral"
    weekly_goal = int(payload.get("weekly_goal", 5))

    if not name:
        raise ValueError("Informe o nome do habito.")
    if weekly_goal < 1 or weekly_goal > 7:
        raise ValueError("A meta semanal precisa ficar entre 1 e 7.")

    with connect() as db:
        cursor = db.execute(
            "INSERT INTO habits (name, category, weekly_goal, created_at) VALUES (?, ?, ?, ?)",
            (name, category, weekly_goal, date.today().isoformat()),
        )
        row = db.execute("SELECT * FROM habits WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def toggle_completion(habit_id):
    today = date.today().isoformat()
    with connect() as db:
        existing = db.execute(
            "SELECT id FROM completions WHERE habit_id = ? AND completed_on = ?",
            (habit_id, today),
        ).fetchone()
        if existing:
            db.execute("DELETE FROM completions WHERE id = ?", (existing["id"],))
            return {"completed_today": False}

        db.execute(
            "INSERT INTO completions (habit_id, completed_on) VALUES (?, ?)",
            (habit_id, today),
        )
        return {"completed_today": True}


def delete_habit(habit_id):
    with connect() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
    return {"deleted": True}


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/habits":
            self.send_json({"habits": get_habits()})
            return

        self.serve_file(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/habits":
                self.send_json(create_habit(self.read_json()), status=201)
                return

            if parsed.path.startswith("/api/habits/") and parsed.path.endswith("/toggle"):
                habit_id = int(parsed.path.split("/")[3])
                self.send_json(toggle_completion(habit_id))
                return

            self.send_error(404)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=400)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/habits/"):
            habit_id = int(parsed.path.split("/")[3])
            self.send_json(delete_habit(habit_id))
            return
        self.send_error(404)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_file(self, path):
        if path == "/":
            path = "/index.html"

        target = (PUBLIC / path.lstrip("/")).resolve()
        public_root = PUBLIC.resolve()
        if not str(target).startswith(str(public_root)) or not target.exists():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("localhost", 8000), AppHandler)
    print("PulseHabits rodando em http://localhost:8000")
    server.serve_forever()
