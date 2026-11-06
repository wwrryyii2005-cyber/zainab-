from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
DB_PATH = Path(os.getenv("APP_DB_PATH", str(BASE_DIR / "data" / "assistant.db")))
WEB_DIR = BASE_DIR / "web"
SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-only-change-this-secret-before-deployment")
BOOTSTRAP_KEY = os.getenv("APP_BOOTSTRAP_KEY", "CHANGE-ME-ADMIN-SETUP-KEY")
TOKEN_LIFETIME = int(os.getenv("APP_TOKEN_MINUTES", "720")) * 60

app = FastAPI(
    title="EyeSpeak AI",
    description="Patient communication and nurse dashboard prototype API",
    version="1.0.0",
)


def classify_patient_request(text: str) -> dict:
    """Lightweight bilingual intent/priority classifier; not a diagnostic AI."""
    t = text.casefold()
    groups = [
        ("Emergency / urgent", "Urgent", ["can't breathe", "cannot breathe", "chest pain", "unconscious", "bleeding", "emergency", "اختناق", "ما اكدر اتنفس", "ضيق نفس", "نزيف", "فاقد الوعي", "ألم صدر", "الم صدر"]),
        ("Pain / discomfort", "High", ["pain", "hurt", "ache", "ألم", "وجع", "يوجع", "اتألم", "تعبان"]),
        ("Breathing / respiratory", "High", ["breath", "cough", "oxygen", "تنفس", "كحة", "سعال", "اوكسجين"]),
        ("Toilet assistance", "Normal", ["toilet", "bathroom", "restroom", "urine", "حمام", "مرحاض", "تبول"]),
        ("Food / drink", "Normal", ["water", "drink", "thirst", "food", "hungry", "meal", "ماء", "مي", "عطشان", "اكل", "طعام", "جوعان"]),
        ("Comfort / positioning", "Normal", ["blanket", "cold", "hot", "position", "turn me", "بطانية", "بردان", "حران", "غير وضعي", "تقليب"]),
        ("Nurse / family contact", "Normal", ["nurse", "family", "call", "ممرض", "ممرضة", "اهلي", "اتصل", "اتصلي"]),
    ]
    for category, priority, words in groups:
        if any(w in t for w in words):
            return {"category": category, "priority": priority, "classification_method": "keyword-assisted"}
    return {"category": "General assistance", "priority": "Normal", "classification_method": "general-fallback"}


def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','nurse','patient')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES users(id),
            request_text TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'button',
            status TEXT NOT NULL DEFAULT 'New'
              CHECK(status IN ('New','Seen','Responded')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
        CREATE INDEX IF NOT EXISTS idx_requests_patient ON requests(patient_id);
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

def hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return base64.b64encode(digest).decode(), base64.b64encode(salt).decode()

def verify_password(password: str, stored_hash: str, stored_salt: str) -> bool:
    try:
        digest, _ = hash_password(password, base64.b64decode(stored_salt))
        return hmac.compare_digest(digest, stored_hash)
    except Exception:
        return False

def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def make_token(user: sqlite3.Row) -> str:
    payload = {
        "uid": user["id"], "role": user["role"],
        "exp": int(time.time()) + TOKEN_LIFETIME,
        "nonce": secrets.token_hex(8),
    }
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + signature

def decode_token(token: str) -> dict:
    try:
        body, signature = token.split(".", 1)
        expected = b64(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please sign in again.")

def current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in.")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    with db() as con:
        row = con.execute(
            "SELECT id, username, full_name, role, active FROM users WHERE id=?",
            (payload["uid"],)
        ).fetchone()
    if not row or not row["active"]:
        raise HTTPException(status_code=401, detail="Account is inactive.")
    return dict(row)

def require(*roles):
    def checker(user: dict = Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return user
    return checker

def log_event(actor_id, action, details=""):
    with db() as con:
        con.execute(
            "INSERT INTO audit_log(actor_id,action,details) VALUES(?,?,?)",
            (actor_id, action, details[:500])
        )

def public_user(row):
    return {"id": row["id"], "username": row["username"],
            "full_name": row["full_name"], "role": row["role"]}

class BootstrapData(BaseModel):
    setup_key: str
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)

class LoginData(BaseModel):
    username: str
    password: str

class UserData(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=10, max_length=128)
    role: str

class RequestData(BaseModel):
    request_text: str = Field(min_length=1, max_length=300)
    source: str = "button"

class StatusData(BaseModel):
    status: str

@app.on_event("startup")
def startup():
    init_db()

@app.get("/api/health")
def health():
    return {"status": "online", "application": "EyeSpeak AI"}

@app.post("/api/setup")
def setup_admin(data: BootstrapData):
    if data.setup_key != BOOTSTRAP_KEY:
        raise HTTPException(status_code=403, detail="Incorrect setup key.")
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count:
            raise HTTPException(status_code=409, detail="Setup already completed.")
        pw_hash, salt = hash_password(data.password)
        cur = con.execute(
            "INSERT INTO users(username,full_name,password_hash,salt,role) VALUES(?,?,?,?,?)",
            (data.username.strip(), data.full_name.strip(), pw_hash, salt, "admin")
        )
        user_id = cur.lastrowid
    log_event(user_id, "system_setup", "Administrator created")
    return {"message": "Administrator created. You can now sign in."}

@app.post("/api/login")
def login(data: LoginData):
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=? AND active=1",
                           (data.username.strip(),)).fetchone()
    if not user or not verify_password(data.password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    log_event(user["id"], "login", "Successful login")
    return {"access_token": make_token(user), "token_type": "bearer",
            "user": public_user(user)}

@app.post("/api/logout")
def logout(user=Depends(current_user)):
    log_event(user["id"], "logout", "User signed out")
    return {"message": "Signed out."}

@app.get("/api/me")
def me(user=Depends(current_user)):
    return user

@app.post("/api/users", status_code=201)
def create_user(data: UserData, admin=Depends(require("admin"))):
    if data.role not in ("nurse", "patient"):
        raise HTTPException(status_code=400, detail="Role must be nurse or patient.")
    pw_hash, salt = hash_password(data.password)
    try:
        with db() as con:
            cur = con.execute(
                "INSERT INTO users(username,full_name,password_hash,salt,role) VALUES(?,?,?,?,?)",
                (data.username.strip(), data.full_name.strip(), pw_hash, salt, data.role)
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already exists.")
    log_event(admin["id"], "user_created", f"{data.role}:{data.username}")
    return {"id": user_id, "username": data.username, "full_name": data.full_name, "role": data.role}

@app.get("/api/users")
def list_users(admin=Depends(require("admin"))):
    with db() as con:
        rows = con.execute(
            "SELECT id,username,full_name,role,active,created_at FROM users ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/requests", status_code=201)
def create_request(data: RequestData, user=Depends(require("patient"))):
    source = data.source if data.source in ("button", "eye_gaze", "desktop", "web") else "button"
    with db() as con:
        cur = con.execute(
            "INSERT INTO requests(patient_id,request_text,source) VALUES(?,?,?)",
            (user["id"], data.request_text.strip(), source)
        )
        request_id = cur.lastrowid
        row = con.execute("""
            SELECT r.*,u.full_name AS patient_name FROM requests r
            JOIN users u ON u.id=r.patient_id WHERE r.id=?
        """, (request_id,)).fetchone()
    log_event(user["id"], "request_created", f"request_id={request_id}")
    result = dict(row)
    result.update(classify_patient_request(result["request_text"]))
    return result

@app.get("/api/requests")
def list_requests(status: Optional[str] = Query(default=None), limit: int = 200,
                  user=Depends(current_user)):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 500.")
    if status and status not in ("New", "Seen", "Responded"):
        raise HTTPException(status_code=400, detail="Invalid status.")
    sql = """SELECT r.*,u.full_name AS patient_name FROM requests r
             JOIN users u ON u.id=r.patient_id"""
    params = []
    clauses = []
    if user["role"] == "patient":
        clauses.append("r.patient_id=?")
        params.append(user["id"])
    if status:
        clauses.append("r.status=?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY r.id DESC LIMIT ?"
    params.append(limit)
    with db() as con:
        rows = con.execute(sql, params).fetchall()
    results = []
    for r in rows:
        item = dict(r)
        item.update(classify_patient_request(item["request_text"]))
        results.append(item)
    return results

@app.patch("/api/requests/{request_id}")
def update_request(request_id: int, data: StatusData,
                   nurse=Depends(require("nurse", "admin"))):
    if data.status not in ("Seen", "Responded"):
        raise HTTPException(status_code=400, detail="Status must be Seen or Responded.")
    with db() as con:
        cur = con.execute(
            "UPDATE requests SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data.status, request_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Request not found.")
        row = con.execute("""
            SELECT r.*,u.full_name AS patient_name FROM requests r
            JOIN users u ON u.id=r.patient_id WHERE r.id=?
        """, (request_id,)).fetchone()
    log_event(nurse["id"], "request_updated", f"request_id={request_id};status={data.status}")
    result = dict(row)
    result.update(classify_patient_request(result["request_text"]))
    return result

@app.get("/api/dashboard/summary")
def summary(nurse=Depends(require("nurse", "admin"))):
    with db() as con:
        rows = con.execute("SELECT status,COUNT(*) AS total FROM requests GROUP BY status").fetchall()
    counts = {"new": 0, "seen": 0, "responded": 0}
    for row in rows:
        counts[row["status"].lower()] = row["total"]
    counts["total"] = sum(counts.values())
    return counts

@app.get("/api/audit")
def audit(limit: int = 100, admin=Depends(require("admin"))):
    limit = max(1, min(limit, 500))
    with db() as con:
        rows = con.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

@app.get("/")
def home():
    return FileResponse(WEB_DIR / "index.html")

@app.get("/manifest.json")
def manifest():
    return FileResponse(WEB_DIR / "manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")
