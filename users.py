"""
유저 조회 관련 라우터.
main.py 는 이 라우터를 include_router 로 등록만 하고,
실제 조회 로직은 모두 여기서 처리한다.
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

# 이 라우터의 모든 엔드포인트는 자동으로 "/users" 접두사가 붙는다.
router = APIRouter(prefix="/users", tags=["users"])


def _require_user_id(x_user_id: int | None) -> int:
    # 별도의 세션/토큰 없이, 로그인 시 프론트가 localStorage 에 저장해둔 유저 id를
    # X-User-Id 헤더로 실어 보내는 방식으로 "나"를 식별한다.
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return x_user_id


@router.get("/me")
def get_current_user(x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    user_id = _require_user_id(x_user_id)

    # main.py 의 get_connection 을 재사용한다.
    # 함수 안에서 import 하는 이유: main.py 가 이 파일(users.py)을 import 하므로,
    # 모듈 최상단에서 서로를 import 하면 순환 import 오류가 발생한다.
    from main import get_connection
    import psycopg2.extras

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, nickname, profile_image FROM users WHERE id = %s;",
                (user_id,),
            )
            user = cur.fetchone()

    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user


class UpdateProfileRequest(BaseModel):
    """회원 정보 수정 요청 바디. 프로필 사진은 아직 다루지 않는다."""

    email: EmailStr
    nickname: str = Field(min_length=1, max_length=50)


@router.put("/me")
def update_current_user(
    payload: UpdateProfileRequest,
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
):
    user_id = _require_user_id(x_user_id)

    from main import get_connection
    import psycopg2.extras

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 다른 유저가 이미 쓰고 있는 이메일로는 바꿀 수 없다 (users.email 은 UNIQUE).
            cur.execute(
                "SELECT id FROM users WHERE email = %s AND id != %s;",
                (payload.email, user_id),
            )
            if cur.fetchone() is not None:
                raise HTTPException(status_code=409, detail="이미 사용 중인 이메일입니다.")

            cur.execute(
                """
                UPDATE users
                SET email = %s, nickname = %s, updated_at = now()
                WHERE id = %s
                RETURNING id, email, nickname, profile_image;
                """,
                (payload.email, payload.nickname, user_id),
            )
            updated_user = cur.fetchone()
            if updated_user is None:
                raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
            conn.commit()

    return updated_user


@router.get("")
def get_users():
    from main import get_connection
    import psycopg2.extras

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, email, nickname, profile_image, created_at FROM users ORDER BY id;"
            )
            return cur.fetchall()
