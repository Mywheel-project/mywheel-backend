import psycopg2.extras
from fastapi import APIRouter, HTTPException, Header
from typing import List

from schemas import CommentCreate, CommentResponse
# posts.py와 동일하게, users.py의 X-User-Id 헤더 기반 인증 방식을 그대로 사용한다.
from users import _require_user_id

router = APIRouter(prefix="/api/posts/{post_id}/comments", tags=["comments"])


def _get_current_user(x_user_id: int | None):
    """posts.py와 같은 방식(users.py의 X-User-Id 헤더)을 이 파일에서도 그대로 사용."""
    user_id = _require_user_id(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, nickname FROM users WHERE id = %s;", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다.")
            return user


# 댓글 등록 (로그인 필요)
@router.post("", response_model=CommentResponse)
def create_comment(post_id: int, comment: CommentCreate, x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    current_user = _get_current_user(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM posts WHERE id = %s;", (post_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

            cur.execute(
                """
                INSERT INTO comments (post_id, content, author, user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, post_id, content, author, created_at, user_id;
                """,
                (post_id, comment.content, current_user["nickname"], current_user["id"])
            )
            new_comment = cur.fetchone()
            conn.commit()
            return new_comment


# 특정 게시글의 댓글 목록 조회 (로그인 불필요)
@router.get("", response_model=List[CommentResponse])
def get_comments(post_id: int):
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, post_id, content, author, created_at, user_id FROM comments WHERE post_id = %s ORDER BY id ASC;",
                (post_id,)
            )
            return cur.fetchall()