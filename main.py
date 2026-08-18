import psycopg2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="mywheel-backend")

# 프론트엔드(Vite 개발 서버)에서 이 API를 호출할 수 있도록 허용한다.
# 5173 포트가 이미 사용 중이면 Vite가 5174, 5175 ... 로 자동으로 옮겨가므로
# 포트를 고정하지 않고 localhost/127.0.0.1의 모든 포트를 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "mywheel",
    "user": "mywheel",
    "password": "mywheel",
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.get("/health")
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
