#!/usr/bin/env python3
"""GLITCHLOG Team website — Python standard-library backend only.

Run: python app.py
Then open: http://127.0.0.1:8000
All project files and uploaded files are kept in this same directory.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import hashlib
import hmac
import http.cookies
import sqlite3
import time
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"
DB_FILE = BASE_DIR / "applications.db"
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
MAX_REQUEST_BYTES = 14 * 1024 * 1024  # 14 MB including multipart overhead
MAX_RESUME_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_TOTAL_BYTES = 10 * 1024 * 1024
SESSIONS: dict[str, dict] = {}
ADMIN_USERNAME = os.environ.get("GLITCHLOG_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("GLITCHLOG_ADMIN_PASSWORD", "ChangeMe-Now-2026")

MEMBERS = [
    {
        "id": 1,
        "name": "علی محمدی",
        "role": "Full Stack Developer",
        "category": "Backend",
        "motto": "کدِ خوب، مسئله را حل می‌کند؛ کدِ عالی، مسئله را ساده می‌کند.",
        "skills": ["Python", "React", "PostgreSQL"],
        "resume_url": "https://github.com/",
        "initials": "ع‌م",
        "tone": "mint",
    },
    {
        "id": 2,
        "name": "سارا رضایی",
        "role": "UI/UX Designer",
        "category": "Design",
        "motto": "تجربه‌های ساده، از فکرهای پیچیده متولد می‌شوند.",
        "skills": ["Figma", "Photoshop", "UI/UX"],
        "resume_url": "https://www.behance.net/",
        "initials": "س‌ر",
        "tone": "violet",
    },
    {
        "id": 3,
        "name": "امیر حسینی",
        "role": "Backend Developer",
        "category": "Backend",
        "motto": "زیر هر رابط خوب، معماری‌ای قابل اعتماد وجود دارد.",
        "skills": ["Python", "Flask", "Docker"],
        "resume_url": "https://github.com/",
        "initials": "ا‌ح",
        "tone": "orange",
    },
    {
        "id": 4,
        "name": "رضا کریمی",
        "role": "Frontend Developer",
        "category": "Frontend",
        "motto": "جزئیات کوچک‌اند که یک محصول را به‌یادماندنی می‌کنند.",
        "skills": ["HTML", "CSS", "JavaScript"],
        "resume_url": "https://github.com/",
        "initials": "ر‌ک",
        "tone": "blue",
    },
    {
        "id": 5,
        "name": "مینا احمدی",
        "role": "Graphic Designer",
        "category": "Design",
        "motto": "هر ایده، قبل از دیده‌شدن، به یک تصویر نیاز دارد.",
        "skills": ["Photoshop", "Illustrator", "Branding"],
        "resume_url": "https://www.behance.net/",
        "initials": "م‌ا",
        "tone": "pink",
    },
    {
        "id": 6,
        "name": "پویا نادری",
        "role": "DevOps Engineer",
        "category": "DevOps",
        "motto": "ساختن مهم است؛ ساختن چیزی که همیشه کار کند مهم‌تر است.",
        "skills": ["Linux", "Docker", "AWS"],
        "resume_url": "https://github.com/",
        "initials": "پ‌ن",
        "tone": "cyan",
    },
]


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
                portfolio_url TEXT NOT NULL DEFAULT '', motto TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL)""")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS anonymous_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                portfolio_url TEXT NOT NULL,
                motto TEXT NOT NULL,
                resume_filename TEXT NOT NULL,
                documents_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def send_json(handler: BaseHTTPRequestHandler, status: int, data: dict) -> None:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def safe_filename(original: str) -> str:
    # Keep only the basename and simple characters; never trust browser paths.
    name = Path(original.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return (name or "upload")[:100]


class GlitchlogHandler(BaseHTTPRequestHandler):
    server_version = "GLITCHLOG/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Log method and path, but avoid leaking form values.
        super().log_message(fmt, *args)

    def _send_static(self) -> None:
        try:
            data = INDEX_FILE.read_bytes()
        except OSError:
            self.send_error(500, "index.html is missing")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _session(self) -> tuple[str | None, dict | None]:
        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookies.get("glitchlog_session")
        token = morsel.value if morsel else None
        return token, SESSIONS.get(token) if token else None

    def _set_session(self, data: dict) -> None:
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = data
        self.send_header("Set-Cookie", f"glitchlog_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400")

    def _json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 100_000:
            raise ValueError("درخواست نامعتبر است.")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict): raise ValueError("داده نامعتبر است.")
        return data

    @staticmethod
    def _hash_password(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
        return salt.hex() + ":" + digest.hex()

    @staticmethod
    def _check_password(password: str, stored: str) -> bool:
        try:
            salt_hex, digest_hex = stored.split(":", 1)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 240_000).hex()
            return hmac.compare_digest(actual, digest_hex)
        except Exception: return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send_static()
            return
        if path == "/glitchlog-logo.jpg":
            try: data=(BASE_DIR / "glitchlog-logo.jpg").read_bytes()
            except OSError: self.send_error(404, "logo missing"); return
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "public, max-age=86400"); self.end_headers(); self.wfile.write(data); return
        if path == "/styles.css":
            try: data=(BASE_DIR / "styles.css").read_bytes()
            except OSError: self.send_error(500, "styles.css is missing"); return
            self.send_response(200); self.send_header("Content-Type", "text/css; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/api/profile-data":
            _, session = self._session()
            if not session or session.get("admin"): send_json(self,403,{"ok":False,"message":"ابتدا وارد حساب کاربری شو."}); return
            with sqlite3.connect(DB_FILE) as con:
                con.row_factory=sqlite3.Row; row=con.execute("SELECT name,phone,portfolio_url,motto FROM users WHERE id=?",(session["id"],)).fetchone()
            if not row: send_json(self,404,{"ok":False,"message":"حساب پیدا نشد."}); return
            send_json(self,200,dict(row)); return
        if path == "/api/members":
            send_json(self, 200, {"members": MEMBERS})
            return
        if path == "/api/health":
            send_json(self, 200, {"ok": True, "app": "GLITCHLOG Team"})
            return
        if path == "/api/me":
            _, session = self._session()
            send_json(self, 200, {"authenticated": bool(session), "user": session})
            return
        if path == "/api/admin/applications":
            _, session = self._session()
            if not session or not session.get("admin"):
                send_json(self, 403, {"ok": False, "message": "فقط مدیر اجازه دسترسی دارد."}); return
            with sqlite3.connect(DB_FILE) as con:
                con.row_factory = sqlite3.Row
                rows = con.execute("SELECT id,name,phone,portfolio_url,motto,resume_filename,documents_json,created_at FROM applications ORDER BY id DESC").fetchall()
            send_json(self, 200, {"applications": [dict(row) for row in rows]}); return
        if path == "/api/admin/anonymous-messages":
            _, session = self._session()
            if not session or not session.get("admin"):
                send_json(self, 403, {"ok": False, "message": "فقط مدیر اجازه دسترسی دارد."}); return
            with sqlite3.connect(DB_FILE) as con:
                con.row_factory = sqlite3.Row
                rows = con.execute("SELECT id,message,created_at FROM anonymous_messages ORDER BY id DESC LIMIT 200").fetchall()
            send_json(self, 200, {"messages": [dict(row) for row in rows]}); return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/anonymous-message":
            try:
                data = self._json_body()
            except Exception as exc:
                send_json(self, 400, {"ok": False, "message": str(exc)}); return
            message = str(data.get("message", "")).strip()
            if len(message) < 3 or len(message) > 3000:
                send_json(self, 400, {"ok": False, "message": "پیام باید بین ۳ تا ۳۰۰۰ نویسه باشد."}); return
            with sqlite3.connect(DB_FILE) as con:
                cur = con.execute("INSERT INTO anonymous_messages(message,created_at) VALUES(?,?)", (message, datetime.now(timezone.utc).isoformat()))
                message_id = cur.lastrowid
            send_json(self, 201, {"ok": True, "message": "پیام ناشناس شما ارسال شد.", "message_id": message_id}); return
        if path in ("/api/signup", "/api/login", "/api/admin/login", "/api/profile", "/api/logout"):
            try: data = self._json_body() if path != "/api/logout" else {}
            except Exception as exc: send_json(self, 400, {"ok": False, "message": str(exc)}); return
            if path == "/api/signup":
                username = str(data.get("username", "")).strip().lower(); password = str(data.get("password", "")); name = str(data.get("name", "")).strip()
                if not re.fullmatch(r"[a-z0-9_.-]{3,30}", username) or len(password) < 10 or len(name) > 100 or not name:
                    send_json(self, 400, {"ok": False, "message": "نام، نام کاربری معتبر و رمز حداقل ۱۰ کاراکتری وارد کن."}); return
                try:
                    with sqlite3.connect(DB_FILE) as con:
                        cur = con.execute("INSERT INTO users(username,password_hash,name,created_at) VALUES(?,?,?,?)", (username,self._hash_password(password),name,datetime.now(timezone.utc).isoformat()))
                        uid = cur.lastrowid
                except sqlite3.IntegrityError:
                    send_json(self, 409, {"ok": False, "message": "این نام کاربری قبلاً ثبت شده است."}); return
                self.send_response(201); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self._set_session({"id":uid,"username":username,"name":name,"admin":False}); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"message":"حساب ساخته شد."},ensure_ascii=False).encode()); return
            if path in ("/api/login", "/api/admin/login"):
                username = str(data.get("username", "")).strip().lower(); password = str(data.get("password", ""))
                if path == "/api/admin/login":
                    if not (hmac.compare_digest(username, ADMIN_USERNAME.lower()) and hmac.compare_digest(password, ADMIN_PASSWORD)):
                        send_json(self, 401, {"ok":False,"message":"نام کاربری یا رمز مدیر اشتباه است."}); return
                    self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self._set_session({"id":0,"username":ADMIN_USERNAME,"name":"مدیر GLITCHLOG","admin":True}); self.end_headers(); self.wfile.write(json.dumps({"ok": True, "message": "ورود مدیر موفق بود."}, ensure_ascii=False).encode()); return
                with sqlite3.connect(DB_FILE) as con:
                    con.row_factory=sqlite3.Row; row=con.execute("SELECT * FROM users WHERE username=?",(username,)).fetchone()
                if not row or not self._check_password(password,row["password_hash"]): send_json(self,401,{"ok":False,"message":"نام کاربری یا رمز عبور اشتباه است."}); return
                user={"id":row["id"],"username":row["username"],"name":row["name"],"admin":False}
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self._set_session(user); self.end_headers(); self.wfile.write(json.dumps({"ok":True,"user":user},ensure_ascii=False).encode()); return
            if path == "/api/profile":
                _, session = self._session()
                if not session or session.get("admin"): send_json(self,403,{"ok":False,"message":"برای ویرایش پروفایل ابتدا با حساب کاربری وارد شو."}); return
                name=str(data.get("name","")).strip(); phone=str(data.get("phone","")).strip(); portfolio=str(data.get("portfolio_url","")).strip(); motto=str(data.get("motto","")).strip()
                if not name or len(name)>100 or len(phone)>30 or len(motto)>600 or (portfolio and not re.match(r"^https?://",portfolio,re.I)):
                    send_json(self,400,{"ok":False,"message":"اطلاعات واردشده معتبر نیست."}); return
                with sqlite3.connect(DB_FILE) as con: con.execute("UPDATE users SET name=?,phone=?,portfolio_url=?,motto=? WHERE id=?",(name,phone,portfolio,motto,session["id"]))
                session["name"]=name; send_json(self,200,{"ok":True,"message":"پروفایل ذخیره شد.","user":session}); return
            if path == "/api/logout":
                token, _ = self._session()
                if token: SESSIONS.pop(token,None)
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Set-Cookie","glitchlog_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"); self.end_headers(); self.wfile.write(b'{"ok":true}'); return

        if path != "/api/apply":
            send_json(self, 404, {"ok": False, "message": "مسیر مورد نظر پیدا نشد."}); return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            send_json(self, 400, {"ok": False, "message": "فرم باید به‌صورت multipart ارسال شود."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            send_json(self, 413, {"ok": False, "message": "حجم درخواست نامعتبر است یا از ۱۴ مگابایت بیشتر است."})
            return

        raw = self.rfile.read(content_length)
        try:
            message_bytes = (
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
                + raw
            )
            message = BytesParser(policy=policy.default).parsebytes(message_bytes)
            fields: dict[str, list[str]] = {}
            files: dict[str, list[tuple[str, bytes]]] = {}
            if not message.is_multipart():
                raise ValueError("multipart parse failed")
            for part in message.iter_parts():
                field_name = part.get_param("name", header="content-disposition")
                if not field_name:
                    continue
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename:
                    files.setdefault(field_name, []).append((filename, payload))
                else:
                    charset = part.get_content_charset() or "utf-8"
                    value = payload.decode(charset, errors="replace").strip()
                    fields.setdefault(field_name, []).append(value)
        except Exception:
            send_json(self, 400, {"ok": False, "message": "خواندن اطلاعات فرم ناموفق بود. دوباره تلاش کنید."})
            return

        def field(name: str) -> str:
            return fields.get(name, [""])[0].strip()

        name = field("name")
        phone = field("phone")
        portfolio_url = field("portfolio")
        motto = field("motto")
        accepted = field("terms") == "on"
        resumes = files.get("resume", [])
        documents = files.get("documents", [])

        if not name or len(name) > 100:
            send_json(self, 400, {"ok": False, "message": "نام و نام خانوادگی را وارد کنید (حداکثر ۱۰۰ نویسه)."})
            return
        phone_digits = re.sub(r"[^0-9+]", "", phone)
        if len(phone_digits) < 8 or len(phone_digits) > 20:
            send_json(self, 400, {"ok": False, "message": "شماره تماس معتبر وارد کنید."})
            return
        if not portfolio_url or len(portfolio_url) > 500 or not re.match(r"^https?://", portfolio_url, re.I):
            send_json(self, 400, {"ok": False, "message": "لینک رزومه باید با http:// یا https:// شروع شود."})
            return
        if not motto or len(motto) > 600:
            send_json(self, 400, {"ok": False, "message": "شعار فردی را وارد کنید (حداکثر ۶۰۰ نویسه)."})
            return
        if not accepted:
            send_json(self, 400, {"ok": False, "message": "برای ثبت درخواست، تأیید قوانین ضروری است."})
            return
        if len(resumes) != 1 or not resumes[0][0]:
            send_json(self, 400, {"ok": False, "message": "یک فایل رزومه HTML انتخاب کنید."})
            return
        resume_original, resume_data = resumes[0]
        if Path(resume_original).suffix.lower() not in (".html", ".htm"):
            send_json(self, 400, {"ok": False, "message": "فرمت رزومه باید HTML یا HTM باشد."})
            return
        if not resume_data or len(resume_data) > MAX_RESUME_BYTES:
            send_json(self, 400, {"ok": False, "message": "حجم رزومه خالی است یا از ۲ مگابایت بیشتر است."})
            return
        documents = [(filename, data) for filename, data in documents if filename and data]
        if not documents:
            send_json(self, 400, {"ok": False, "message": "حداقل یک فایل مدرک انتخاب کنید."})
            return
        allowed_docs = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".zip"}
        if any(Path(filename).suffix.lower() not in allowed_docs for filename, _ in documents):
            send_json(self, 400, {"ok": False, "message": "مدارک فقط می‌توانند PDF، تصویر، DOC، DOCX یا ZIP باشند."})
            return
        total_docs = sum(len(data) for _, data in documents)
        if total_docs > MAX_DOCUMENT_TOTAL_BYTES:
            send_json(self, 400, {"ok": False, "message": "حجم مجموع مدارک نباید بیشتر از ۱۰ مگابایت باشد."})
            return
        if any(len(data) > 5 * 1024 * 1024 for _, data in documents):
            send_json(self, 400, {"ok": False, "message": "حجم هر فایل مدرک نباید بیشتر از ۵ مگابایت باشد."})
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = secrets.token_hex(4)
        saved_paths: list[Path] = []
        try:
            resume_name = f"upload_resume_{stamp}_{token}_{safe_filename(resume_original)}"
            resume_path = BASE_DIR / resume_name
            resume_path.write_bytes(resume_data)
            saved_paths.append(resume_path)

            saved_documents = []
            for index, (original, data) in enumerate(documents, start=1):
                stored_name = f"upload_doc_{stamp}_{token}_{index}_{safe_filename(original)}"
                stored_path = BASE_DIR / stored_name
                stored_path.write_bytes(data)
                saved_paths.append(stored_path)
                saved_documents.append({"original_name": safe_filename(original), "stored_name": stored_name, "size": len(data)})

            with sqlite3.connect(DB_FILE) as connection:
                connection.execute(
                    "INSERT INTO applications (name, phone, portfolio_url, motto, resume_filename, documents_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, phone, portfolio_url, motto, resume_name,
                     json.dumps(saved_documents, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
                )
        except Exception:
            for saved_path in saved_paths:
                try:
                    saved_path.unlink(missing_ok=True)
                except OSError:
                    pass
            send_json(self, 500, {"ok": False, "message": "ذخیره درخواست انجام نشد. فضای دیسک و مجوز نوشتن را بررسی کنید."})
            return

        send_json(self, 201, {
            "ok": True,
            "message": "درخواست شما با موفقیت ثبت شد. فایل‌ها در کنار app.py ذخیره شدند.",
            "application_id": self._last_application_id(),
        })

    @staticmethod
    def _last_application_id() -> int | None:
        try:
            with sqlite3.connect(DB_FILE) as connection:
                row = connection.execute("SELECT MAX(id) FROM applications").fetchone()
                return int(row[0]) if row and row[0] is not None else None
        except sqlite3.Error:
            return None


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), GlitchlogHandler)
    print("\n  GLITCHLOG Team website is running")
    print(f"  Open: http://{HOST}:{PORT}")
    print("  Stop with Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
