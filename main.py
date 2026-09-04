import psycopg2.extras
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database1 import get_connection, init_db
from routers import posts, comments, auth1

app = FastAPI(title="mywheel-backend")

# 프론트엔드(React/Vite)와의 통신을 위한 CORS 설정
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버 시작 시 테이블 초기화
@app.on_event("startup")
def on_startup():
    init_db()

# 라우터 등록
app.include_router(auth1.router)
app.include_router(posts.router)
app.include_router(comments.router)


# ------------------ [기본 엔드포인트] ------------------

@app.get("/")
def read_root():
    return {"message": "MyWheel 백엔드 서버가 정상 작동 중입니다!"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/users")
def get_users():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, username, email, created_at FROM users ORDER BY id;")
            return cur.fetchall()
