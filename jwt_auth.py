"""
JWT 발급/검증 공통 모듈.
로그인 성공 시 서버가 서명한 access token 을 발급하고,
보호된 API 는 Authorization: Bearer <token> 헤더를 검증해 "나"를 식별한다.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY 환경 변수가 설정되어 있지 않습니다.")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_user_id(authorization: str | None) -> int | None:
    """Authorization 헤더에서 유저 id 를 꺼낸다. 누락/형식 오류/검증 실패 시 None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        # exp 가 없는 토큰은 영구 토큰이 되므로 exp/sub 를 필수로 요구한다.
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def get_current_user_id(authorization: str | None = Header(default=None)) -> int:
    """로그인이 반드시 필요한 API 에서 사용하는 의존성."""
    user_id = _decode_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user_id


def get_current_user_id_optional(authorization: str | None = Header(default=None)) -> int | None:
    """로그인이 없어도 되지만, 로그인했다면 누군지 알고 싶은 API 에서 사용하는 의존성."""
    return _decode_user_id(authorization)
