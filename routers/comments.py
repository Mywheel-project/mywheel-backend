import psycopg2.extras
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from database import get_connection
from schemas import CommentCreate, CommentResponse
from auth import get_current_user

router = APIRouter(prefix="/api/posts/{post_id}/comments", tags=["comments"])


# 댓글 등록 (로그인 필요)
@router.post("", response_model=CommentResponse)
def create_comment(post_id: int, comment: CommentCreate, current_user=Depends(get_current_user)):
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
                (post_id, comment.content, current_user["username"], current_user["id"])
            )
            new_comment = cur.fetchone()
            conn.commit()
            return new_comment


# 특정 게시글의 댓글 목록 조회 (로그인 불필요)
@router.get("", response_model=List[CommentResponse])
def get_comments(post_id: int):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, post_id, content, author, created_at, user_id FROM comments WHERE post_id = %s ORDER BY id ASC;",
                (post_id,)
            )
            return cur.fetchall()