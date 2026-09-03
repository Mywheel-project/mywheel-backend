import os
import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import custom
from database import engine, Base
import models

app = FastAPI(title="mywheel-backend", version="1.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 이미지 파일 서빙 (/static/results/...)
STATIC_PATH = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_PATH, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

# DB 테이블 자동 생성 (없으면 생성, 있으면 무시)
Base.metadata.create_all(bind=engine)   

#  단 1줄로 등록 (prefix를 /api/v1 로 통일)
app.include_router(custom.router, prefix="/api/v1")

# DB 설정 (경수 코드)
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mywheel",
    "user": "mywheel",
    "password": "mywheel",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.get("/health", tags=["default"])
def health():
    return {"status": "ok"}

@app.get("/users", tags=["default"])
def get_users():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, name, email, created_at FROM users ORDER BY id;")
            return cur.fetchall()