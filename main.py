import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

app = FastAPI(title="mywheel-backend")

# 1. 프론트엔드(React/Vite)와의 통신을 위한 CORS 설정
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],      # 모든 HTTP Method 허용 (GET, POST 등)
    allow_headers=["*"],      # 모든 Header 허용
)

# DB 접속 설정
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mywheel",
    "user": "mywheel",
    "password": "mywheel",
}

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

# 서버 시작 시 커뮤니티(posts) 테이블이 없으면 자동 생성
@app.on_event("startup")
def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(200) NOT NULL,
                    content TEXT NOT NULL,
                    author VARCHAR(50) DEFAULT '익명',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

# Pydantic 데이터 모델 (요청 및 응답 규격)
class PostCreate(BaseModel):
    title: str
    content: str
    author: Optional[str] = "익명"

class PostResponse(BaseModel):
    id: int
    title: str
    content: str
    author: str
    created_at: datetime


# ------------------ [API 엔드포인트] ------------------

@app.get("/")
def read_root():
    return {"message": "MyWheel 백엔드 서버가 정상 작동 중입니다!"}

@app.get("/health")
def health():
    return {"status": "ok"}

# 기존 유저 조회 API
@app.get("/users")
def get_users():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, name, email, created_at FROM users ORDER BY id;")
            return cur.fetchall()

# 2. 커뮤니티 게시글 등록 (DB 저장)
@app.post("/api/posts", response_model=PostResponse)
def create_post(post: PostCreate):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO posts (title, content, author)
                VALUES (%s, %s, %s)
                RETURNING id, title, content, author, created_at;
                """,
                (post.title, post.content, post.author)
            )
            new_post = cur.fetchone()
            conn.commit()
            return new_post

# 3. 커뮤니티 게시글 목록 조회
@app.get("/api/posts", response_model=List[PostResponse])
def get_posts():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title, content, author, created_at FROM posts ORDER BY id DESC;")
            return cur.fetchall()

# 4. 게시글 수정용 요청 모델
class PostUpdate(BaseModel):
    title: str
    content: str

# 5. 게시글 단건 조회 (수정 페이지에서 기존 내용 불러올 때 사용)
@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, content, author, created_at FROM posts WHERE id = %s;",
                (post_id,)
            )
            post = cur.fetchone()
            if not post:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            return post

# 6. 게시글 수정
@app.put("/api/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post: PostUpdate):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE posts
                SET title = %s, content = %s
                WHERE id = %s
                RETURNING id, title, content, author, created_at;
                """,
                (post.title, post.content, post_id)
            )
            updated_post = cur.fetchone()
            conn.commit()
            if not updated_post:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            return updated_post

# 7. 게시글 삭제
@app.delete("/api/posts/{post_id}")
def delete_post(post_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM posts WHERE id = %s RETURNING id;", (post_id,))
            deleted = cur.fetchone()
            conn.commit()
            if not deleted:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            return {"message": "게시글이 삭제되었습니다.", "id": post_id}