"""
posts / comments 라우터가 함께 쓰는 인증 의존성.

main 프로젝트(main 브랜치)는 JWT 토큰을 쓰지 않고, 로그인한 유저의 id를
프론트엔드가 "X-User-Id" 헤더에 실어 보내는 방식으로 식별한다 (users.py 참고).
posts/comments는 원래 JWT 기반(auth.py)으로 작성되어 있었는데, main 방식에 맞춰
여기서 새로 정의한다.
"""

import psycopg2.extras
from fastapi import Header, HTTPException
from typing import Optional


def get_current_user(x_user_id: Optional[int] = Header(default=None, alias="X-User-Id")):
    """로그인이 반드시 필요한 API에서 사용."""
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    # main.py 의 get_connection 을 재사용한다. 순환 import 방지를 위해 함수 안에서 import.
    from main import get_connection

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, nickname FROM users WHERE id = %s;", (x_user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다.")
            return user


def get_current_user_optional(x_user_id: Optional[int] = Header(default=None, alias="X-User-Id")):
    """로그인이 없어도 되지만, 로그인했다면 누군지 알고 싶은 API에서 사용."""
    if x_user_id is None:
        return None
    try:
        return get_current_user(x_user_id)
    except HTTPException:
        return None
