import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Depends

from database import get_connection
from schemas import UserSignup, UserLogin, UserResponse, TokenResponse
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


# 회원가입
@router.post("/signup", response_model=UserResponse)
def signup(user: UserSignup):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO users (username, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, username, email, created_at;
                    """,
                    (user.username, user.email, hash_password(user.password))
                )
                new_user = cur.fetchone()
                conn.commit()
                return new_user
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise HTTPException(status_code=400, detail="이미 사용 중인 아이디 또는 이메일입니다.")


# 로그인
@router.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, email, password_hash, created_at FROM users WHERE email = %s;",
                (credentials.email,)
            )
            user = cur.fetchone()

            if not user or not verify_password(credentials.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

            token = create_access_token(user_id=user["id"], username=user["username"])

            return {
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "created_at": user["created_at"],
                },
            }


# 현재 로그인한 유저 정보 조회 (토큰 유효성 확인용)
@router.get("/me", response_model=UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user