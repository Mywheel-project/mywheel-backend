import psycopg2.extras
from fastapi import APIRouter, HTTPException, Depends
from typing import List

from database import get_connection
from schemas import PostCreate, PostUpdate, PostResponse
from auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _attach_liked_by_me(cur, post: dict, current_user) -> dict:
    """post 딕셔너리에 현재 로그인한 유저가 좋아요를 눌렀는지 여부를 채워넣음"""
    if current_user:
        cur.execute(
            "SELECT 1 FROM likes WHERE post_id = %s AND user_id = %s;",
            (post["id"], current_user["id"])
        )
        post["liked_by_me"] = cur.fetchone() is not None
    else:
        post["liked_by_me"] = False
    return post


# 게시글 등록 (로그인 필요)
@router.post("", response_model=PostResponse)
def create_post(post: PostCreate, current_user=Depends(get_current_user)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO posts (title, content, author, user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, content, author, created_at, likes_count, view_count, user_id;
                """,
                (post.title, post.content, current_user["username"], current_user["id"])
            )
            new_post = cur.fetchone()
            conn.commit()
            new_post["liked_by_me"] = False
            return new_post


# 게시글 목록 조회 (로그인 불필요, 로그인했다면 liked_by_me도 같이 내려줌)
@router.get("", response_model=List[PostResponse])
def get_posts(current_user=Depends(get_current_user_optional)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, title, content, author, created_at, likes_count, view_count, user_id FROM posts ORDER BY id DESC;"
            )
            posts = cur.fetchall()
            for post in posts:
                _attach_liked_by_me(cur, post, current_user)
            return posts


# 🔥 핫게시물: 최근 7일 이내 게시글 중 (좋아요×3 + 조회수×1) 점수 상위 3개
# 주의: /{post_id} 보다 반드시 먼저 등록해야 "hot"이 post_id로 잘못 해석되지 않음
@router.get("/hot", response_model=List[PostResponse])
def get_hot_posts(current_user=Depends(get_current_user_optional)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. 최근 7일 이내 글에서 상위 3개
            cur.execute(
                """
                SELECT id, title, content, author, created_at, likes_count, view_count, user_id,
                       (likes_count * 3 + view_count * 1) AS hot_score
                FROM posts
                WHERE created_at > NOW() - INTERVAL '7 days'
                ORDER BY hot_score DESC, id DESC
                LIMIT 3;
                """
            )
            posts = cur.fetchall()

            # 2. 3개가 안 채워졌으면, 이미 뽑힌 글을 제외하고 전체 기간에서 나머지 채우기
            remaining = 3 - len(posts)
            if remaining > 0:
                already_picked_ids = [p["id"] for p in posts] or [0]  # 빈 리스트면 IN 절 에러 방지용 더미값
                cur.execute(
                    """
                    SELECT id, title, content, author, created_at, likes_count, view_count, user_id,
                           (likes_count * 3 + view_count * 1) AS hot_score
                    FROM posts
                    WHERE id != ALL(%s)
                    ORDER BY hot_score DESC, id DESC
                    LIMIT %s;
                    """,
                    (already_picked_ids, remaining)
                )
                posts.extend(cur.fetchall())

            for post in posts:
                post.pop("hot_score", None)
                _attach_liked_by_me(cur, post, current_user)
            return posts


# 게시글 단건 조회 (조회수 자동 증가, 로그인 여부에 따라 liked_by_me 포함)
@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: int, current_user=Depends(get_current_user_optional)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE posts
                SET view_count = view_count + 1
                WHERE id = %s
                RETURNING id, title, content, author, created_at, likes_count, view_count, user_id;
                """,
                (post_id,)
            )
            post = cur.fetchone()
            conn.commit()
            if not post:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            _attach_liked_by_me(cur, post, current_user)
            return post


# 게시글 수정 (로그인 필요 + 작성자 본인만 가능)
@router.put("/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post: PostUpdate, current_user=Depends(get_current_user)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT user_id FROM posts WHERE id = %s;", (post_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            if existing["user_id"] != current_user["id"]:
                raise HTTPException(status_code=403, detail="본인이 작성한 게시글만 수정할 수 있습니다.")

            cur.execute(
                """
                UPDATE posts
                SET title = %s, content = %s
                WHERE id = %s
                RETURNING id, title, content, author, created_at, likes_count, view_count, user_id;
                """,
                (post.title, post.content, post_id)
            )
            updated_post = cur.fetchone()
            conn.commit()
            _attach_liked_by_me(cur, updated_post, current_user)
            return updated_post


# 게시글 삭제 (로그인 필요 + 작성자 본인만 가능)
@router.delete("/{post_id}")
def delete_post(post_id: int, current_user=Depends(get_current_user)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT user_id FROM posts WHERE id = %s;", (post_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")
            if existing["user_id"] != current_user["id"]:
                raise HTTPException(status_code=403, detail="본인이 작성한 게시글만 삭제할 수 있습니다.")

            cur.execute("DELETE FROM posts WHERE id = %s;", (post_id,))
            conn.commit()
            return {"message": "게시글이 삭제되었습니다.", "id": post_id}


# 좋아요 토글 (로그인 필요, 이미 눌렀으면 취소 / 안 눌렀으면 추가)
@router.post("/{post_id}/like", response_model=PostResponse)
def toggle_like(post_id: int, current_user=Depends(get_current_user)):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM posts WHERE id = %s;", (post_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="게시글을 찾을 수 없습니다.")

            cur.execute(
                "SELECT id FROM likes WHERE post_id = %s AND user_id = %s;",
                (post_id, current_user["id"])
            )
            existing_like = cur.fetchone()

            if existing_like:
                cur.execute("DELETE FROM likes WHERE id = %s;", (existing_like["id"],))
                cur.execute(
                    "UPDATE posts SET likes_count = likes_count - 1 WHERE id = %s;",
                    (post_id,)
                )
            else:
                cur.execute(
                    "INSERT INTO likes (post_id, user_id) VALUES (%s, %s);",
                    (post_id, current_user["id"])
                )
                cur.execute(
                    "UPDATE posts SET likes_count = likes_count + 1 WHERE id = %s;",
                    (post_id,)
                )

            cur.execute(
                "SELECT id, title, content, author, created_at, likes_count, view_count, user_id FROM posts WHERE id = %s;",
                (post_id,)
            )
            updated_post = cur.fetchone()
            conn.commit()
            _attach_liked_by_me(cur, updated_post, current_user)
            return updated_post