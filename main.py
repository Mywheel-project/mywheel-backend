
import os
import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 양쪽 데이터베이스 설정 임포트
from database import engine, Base
from database1 import get_connection, init_db
import models

# 양쪽 라우터 모두 임포트
from routers import posts, comments, auth1, custom

app = FastAPI(title="mywheel-backend", version="1.0.0")
# CORS 설정

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",

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

# 회원가입/로그인(/auth/...)은 auth.py, 유저 조회(/users/...)는 users.py,
# 네이버 지도 연동과 정비업체 조회(/map/...)는 map.py 에 정의되어 있다.
# 파일 하단에서 import 하는 이유는 각 라우터가 get_connection 을 함수 내부에서
# 다시 import 해가기 때문에(순환 import 방지), main 모듈이 먼저 완성된 뒤 연결되어야 한다.
from auth import router as auth_router
from users import router as users_router
from map import router as map_router

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(map_router)
