from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import csv
import hashlib
import io
import json
import mimetypes
import secrets
import sqlite3
from datetime import date, datetime, timedelta


ROOT = Path(__file__).parent
DB_PATH = ROOT / "pulsehabits.db"
PUBLIC = ROOT / "public"


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def row_to_dict(row):
    return {key: row[key] for key in row.keys()}


def column_exists(db, table, column):
    columns = db.execute(f"PRAGMA table_info({table})").fetchall()
    return any(item["name"] == column for item in columns)


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def parse_day(value):
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def week_start(day):
    return day - timedelta(days=day.weekday())


def init_db():
    with connect() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
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
        if not column_exists(db, "habits", "user_id"):
            db.execute("ALTER TABLE habits ADD COLUMN user_id INTEGER")

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

        demo = db.execute("SELECT id FROM users WHERE username = ?", ("demo",)).fetchone()
        if not demo:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                ("demo", hash_password("demo123"), date.today().isoformat()),
            )
            demo_id = cursor.lastrowid
        else:
            demo_id = demo["id"]

        db.execute("UPDATE habits SET user_id = ? WHERE user_id IS NULL", (demo_id,))
        count = db.execute("SELECT COUNT(*) AS total FROM habits WHERE user_id = ?", (demo_id,)).fetchone()["total"]
        if count == 0:
            today = date.today().isoformat()
            db.executemany(
                """
                INSERT INTO habits (name, category, weekly_goal, created_at, user_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("Estudar 40 minutos", "Estudos", 5, today, demo_id),
                    ("Treinar ou caminhar", "Saude", 4, today, demo_id),
                    ("Ler 10 paginas", "Foco", 5, today, demo_id),
                ],
            )


def create_user(username, password):
    username = username.strip().lower()
    if len(username) < 3:
        raise ValueError("Use um usuario com pelo menos 3 caracteres.")
    if len(password) < 4:
        raise ValueError("Use uma senha com pelo menos 4 caracteres.")

    with connect() as db:
        try:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), date.today().isoformat()),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("Esse usuario ja existe.") from error
        user_id = cursor.lastrowid
    return create_session(user_id)


def login_user(username, password):
    username = username.strip().lower()
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise ValueError("Usuario ou senha invalidos.")
        return create_session(user["id"])


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, datetime.now().isoformat(timespec="seconds")),
        )
        user = db.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
    return token, row_to_dict(user)


def get_user_from_token(token):
    if not token:
        return None
    with connect() as db:
        row = db.execute(
            """
            SELECT users.id, users.username
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ?
            """,
            (token,),
        ).fetchone()
        return row_to_dict(row) if row else None


def delete_session(token):
    if token:
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_habits(user_id):
    today = date.today()
    start = week_start(today)
    end = start + timedelta(days=6)
    range_start = today - timedelta(days=13)

    with connect() as db:
        habits = [
            row_to_dict(row)
            for row in db.execute(
                "SELECT * FROM habits WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            )
        ]
        completions = db.execute(
            """
            SELECT habit_id, completed_on
            FROM completions
            JOIN habits ON habits.id = completions.habit_id
            WHERE habits.user_id = ? AND completed_on BETWEEN ? AND ?
            """,
            (user_id, range_start.isoformat(), end.isoformat()),
        ).fetchall()

    completed_by_habit = {}
    for item in completions:
        completed_by_habit.setdefault(item["habit_id"], set()).add(item["completed_on"])

    days = [(range_start + timedelta(days=index)).isoformat() for index in range(14)]
    for habit in habits:
        dates = completed_by_habit.get(habit["id"], set())
        week_dates = [item for item in dates if start.isoformat() <= item <= end.isoformat()]
        habit["completed_today"] = today.isoformat() in dates
        habit["week_count"] = len(week_dates)
        habit["progress"] = min(100, round((len(week_dates) / habit["weekly_goal"]) * 100))
        habit["streak"] = calculate_streak(dates, today)
        habit["history"] = [{"date": item, "done": item in dates} for item in days]

    return habits


def calculate_streak(completed_dates, start_day):
    streak = 0
    cursor = start_day
    while cursor.isoformat() in completed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_history(user_id, days=30):
    days = max(7, min(int(days), 90))
    today = date.today()
    start = today - timedelta(days=days - 1)

    with connect() as db:
        habit_count = db.execute(
            "SELECT COUNT(*) AS total FROM habits WHERE user_id = ?",
            (user_id,),
        ).fetchone()["total"]
        rows = db.execute(
            """
            SELECT completed_on, COUNT(*) AS total
            FROM completions
            JOIN habits ON habits.id = completions.habit_id
            WHERE habits.user_id = ? AND completed_on BETWEEN ? AND ?
            GROUP BY completed_on
            ORDER BY completed_on
            """,
            (user_id, start.isoformat(), today.isoformat()),
        ).fetchall()

    counts = {row["completed_on"]: row["total"] for row in rows}
    series = []
    for index in range(days):
        current = start + timedelta(days=index)
        total = counts.get(current.isoformat(), 0)
        percent = 0 if habit_count == 0 else round((total / habit_count) * 100)
        series.append({"date": current.isoformat(), "total": total, "percent": min(100, percent)})
    return {"days": series, "habit_count": habit_count}


def create_habit(user_id, payload):
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "Geral")).strip() or "Geral"
    weekly_goal = int(payload.get("weekly_goal", 5))

    if not name:
        raise ValueError("Informe o nome do habito.")
    if weekly_goal < 1 or weekly_goal > 7:
        raise ValueError("A meta semanal precisa ficar entre 1 e 7.")

    with connect() as db:
        cursor = db.execute(
            """
            INSERT INTO habits (name, category, weekly_goal, created_at, user_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, category, weekly_goal, date.today().isoformat(), user_id),
        )
        row = db.execute("SELECT * FROM habits WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def update_habit(user_id, habit_id, payload):
    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "Geral")).strip() or "Geral"
    weekly_goal = int(payload.get("weekly_goal", 5))
    if not name:
        raise ValueError("Informe o nome do habito.")
    if weekly_goal < 1 or weekly_goal > 7:
        raise ValueError("A meta semanal precisa ficar entre 1 e 7.")

    with connect() as db:
        db.execute(
            """
            UPDATE habits
            SET name = ?, category = ?, weekly_goal = ?
            WHERE id = ? AND user_id = ?
            """,
            (name, category, weekly_goal, habit_id, user_id),
        )
    return {"updated": True}


def toggle_completion(user_id, habit_id, completed_on):
    selected_day = parse_day(completed_on).isoformat()
    with connect() as db:
        habit = db.execute(
            "SELECT id FROM habits WHERE id = ? AND user_id = ?",
            (habit_id, user_id),
        ).fetchone()
        if not habit:
            raise ValueError("Habito nao encontrado.")

        existing = db.execute(
            "SELECT id FROM completions WHERE habit_id = ? AND completed_on = ?",
            (habit_id, selected_day),
        ).fetchone()
        if existing:
            db.execute("DELETE FROM completions WHERE id = ?", (existing["id"],))
            return {"completed": False, "date": selected_day}

        db.execute(
            "INSERT INTO completions (habit_id, completed_on) VALUES (?, ?)",
            (habit_id, selected_day),
        )
        return {"completed": True, "date": selected_day}


def delete_habit(user_id, habit_id):
    with connect() as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM habits WHERE id = ? AND user_id = ?", (habit_id, user_id))
    return {"deleted": True}


def export_csv(user_id):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["habit", "category", "weekly_goal", "completed_on"])
    with connect() as db:
        rows = db.execute(
            """
            SELECT habits.name, habits.category, habits.weekly_goal, completions.completed_on
            FROM habits
            LEFT JOIN completions ON completions.habit_id = habits.id
            WHERE habits.user_id = ?
            ORDER BY completions.completed_on DESC, habits.name
            """,
            (user_id,),
        ).fetchall()
    for row in rows:
        writer.writerow([row["name"], row["category"], row["weekly_goal"], row["completed_on"] or ""])
    return output.getvalue().encode("utf-8")


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/me":
            user = self.current_user()
            self.send_json({"user": user})
            return

        if parsed.path == "/api/habits":
            user = self.require_user()
            if not user:
                return
            self.send_json({"habits": get_habits(user["id"])})
            return

        if parsed.path == "/api/history":
            user = self.require_user()
            if not user:
                return
            query = parse_qs(parsed.query)
            days = query.get("days", ["30"])[0]
            self.send_json(get_history(user["id"], days))
            return

        if parsed.path == "/api/export.csv":
            user = self.require_user()
            if not user:
                return
            self.send_bytes(export_csv(user["id"]), "text/csv; charset=utf-8", "pulsehabits.csv")
            return

        self.serve_file(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/register":
                token, user = create_user(**self.read_json())
                self.send_session_json(token, {"user": user}, status=201)
                return

            if parsed.path == "/api/login":
                token, user = login_user(**self.read_json())
                self.send_session_json(token, {"user": user})
                return

            if parsed.path == "/api/logout":
                delete_session(self.session_token())
                self.send_session_json("", {"logged_out": True}, max_age=0)
                return

            user = self.require_user()
            if not user:
                return

            if parsed.path == "/api/habits":
                self.send_json(create_habit(user["id"], self.read_json()), status=201)
                return

            if parsed.path.startswith("/api/habits/") and parsed.path.endswith("/toggle"):
                habit_id = int(parsed.path.split("/")[3])
                payload = self.read_json()
                self.send_json(toggle_completion(user["id"], habit_id, payload.get("date")))
                return

            self.send_error(404)
        except (TypeError, ValueError, sqlite3.IntegrityError) as error:
            self.send_json({"error": str(error)}, status=400)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        try:
            user = self.require_user()
            if not user:
                return
            if parsed.path.startswith("/api/habits/"):
                habit_id = int(parsed.path.split("/")[3])
                self.send_json(update_habit(user["id"], habit_id, self.read_json()))
                return
            self.send_error(404)
        except ValueError as error:
            self.send_json({"error": str(error)}, status=400)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        user = self.require_user()
        if not user:
            return
        if parsed.path.startswith("/api/habits/"):
            habit_id = int(parsed.path.split("/")[3])
            self.send_json(delete_habit(user["id"], habit_id))
            return
        self.send_error(404)

    def session_token(self):
        header = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(header)
        morsel = jar.get("pulse_session")
        return morsel.value if morsel else ""

    def current_user(self):
        return get_user_from_token(self.session_token())

    def require_user(self):
        user = self.current_user()
        if user:
            return user
        self.send_json({"error": "Faca login para continuar."}, status=401)
        return None

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_session_json(self, token, payload, status=200, max_age=60 * 60 * 24 * 30):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        cookie = f"pulse_session={token}; Path=/; SameSite=Lax; Max-Age={max_age}; HttpOnly"
        self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type, filename):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
