import psycopg2.extras
from fastapi import APIRouter, HTTPException, Header, Query
from typing import List

from schemas import PostCreate, PostUpdate, PostResponse
# main 프로젝트는 JWT 대신 X-User-Id 헤더로 로그인 유저를 식별한다.
# 별도 deps.py를 새로 만드는 대신, users.py의 _require_user_id를 그대로 재사용한다.
from users import _require_user_id
from fastapi import Form, File, UploadFile
import os
import uuid

router = APIRouter(prefix="/api/posts", tags=["posts"])

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "community")
os.makedirs(STATIC_DIR, exist_ok=True)
BASE_URL = "http://localhost:8000"


def _get_current_user(x_user_id: int | None):
    """로그인이 반드시 필요한 API에서 사용. users.py의 X-User-Id 헤더 방식을 그대로 따른다."""
    user_id = _require_user_id(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, nickname FROM users WHERE id = %s;", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=401, detail="존재하지 않는 사용자입니다.")
            return user


def _get_current_user_optional(x_user_id: int | None):
    """로그인이 없어도 되지만, 로그인했다면 누군지 알고 싶은 API에서 사용."""
    if x_user_id is None:
        return None
    try:
        return _get_current_user(x_user_id)
    except HTTPException:
        return None


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

def _save_image_locally(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(STATIC_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(file.file.read())
    return f"{BASE_URL}/static/community/{filename}"


def _attach_images(cur, post: dict) -> dict:
    cur.execute(
        "SELECT image_url FROM post_images WHERE post_id = %s ORDER BY id;",
        (post["id"],)
    )
    rows = cur.fetchall()
    post["images"] = [row["image_url"] for row in rows]
    return post

# 게시글 등록 (로그인 필요)
@router.post("", response_model=PostResponse)
def create_post(
    title: str = Form(...),
    content: str = Form(...),
    images: List[UploadFile] = File(default=[]),
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
):
    current_user = _get_current_user(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO posts (title, content, author, user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, content, author, created_at, likes_count, view_count, user_id;
                """,
                (title, content, current_user["nickname"], current_user["id"])
            )
            new_post = cur.fetchone()

            image_urls = []
            for img in images:
                if img.filename:
                    url = _save_image_locally(img)
                    image_urls.append(url)
                    cur.execute(
                        "INSERT INTO post_images (post_id, image_url) VALUES (%s, %s);",
                        (new_post["id"], url)
                    )

            conn.commit()
            new_post["liked_by_me"] = False
            new_post["images"] = image_urls
            return new_post


# search 쿼리 파라미터가 있으면 제목/내용에 LIKE 검색 적용
@router.get("", response_model=List[PostResponse])
def get_posts(
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    search: str | None = Query(default=None),
):
    current_user = _get_current_user_optional(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if search:
                 keyword = f"%{search.replace(' ', '')}%"
                 cur.execute(
                    """
                    SELECT id, title, content, author, created_at, likes_count, view_count, user_id
                    FROM posts
                    WHERE REPLACE(title, ' ', '') ILIKE %s OR REPLACE(content, ' ', '') ILIKE %s
                    ORDER BY id DESC;
                    """,
                    (keyword, keyword)
                )
            else:
                cur.execute(
                    "SELECT id, title, content, author, created_at, likes_count, view_count, user_id FROM posts ORDER BY id DESC;"
                )
            posts = cur.fetchall()
            for post in posts:
                post = _attach_liked_by_me(cur, post, current_user)
                post = _attach_images(cur, post)
            return posts


# 🔥 핫게시물: 최근 7일 이내 게시글 중 (좋아요×3 + 조회수×1) 점수 상위 3개
# 주의: /{post_id} 보다 반드시 먼저 등록해야 "hot"이 post_id로 잘못 해석되지 않음
@router.get("/hot", response_model=List[PostResponse])
def get_hot_posts(x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    current_user = _get_current_user_optional(x_user_id)
    from main import get_connection
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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

            remaining = 3 - len(posts)
            if remaining > 0:
                already_picked_ids = [p["id"] for p in posts] or [0]
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
                post = _attach_images(cur, post)
            return posts


# 게시글 단건 조회 (조회수 자동 증가, 로그인 여부에 따라 liked_by_me 포함)
@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: int, x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    current_user = _get_current_user_optional(x_user_id)
    from main import get_connection
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
            post = _attach_images(cur, post)
            return post


# 게시글 수정 (로그인 필요 + 작성자 본인만 가능)
@router.put("/{post_id}", response_model=PostResponse)
def update_post(
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    existing_images: List[str] = Form(default=[]),
    images: List[UploadFile] = File(default=[]),
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
):
    current_user = _get_current_user(x_user_id)
    from main import get_connection
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
                (title, content, post_id)
            )
            updated_post = cur.fetchone()

            # 프론트에서 "남기겠다"고 보낸 URL(existing_images)에 없는 기존 이미지는 삭제
            cur.execute(
                "SELECT id, image_url FROM post_images WHERE post_id = %s;",
                (post_id,)
            )
            current_rows = cur.fetchall()
            for row in current_rows:
                if row["image_url"] not in existing_images:
                    cur.execute("DELETE FROM post_images WHERE id = %s;", (row["id"],))
                    filename = row["image_url"].split("/")[-1]
                    filepath = os.path.join(STATIC_DIR, filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)

            # 새로 첨부된 이미지 저장
            for img in images:
                if img.filename:
                    url = _save_image_locally(img)
                    cur.execute(
                        "INSERT INTO post_images (post_id, image_url) VALUES (%s, %s);",
                        (post_id, url)
                    )

            conn.commit()
            _attach_liked_by_me(cur, updated_post, current_user)
            updated_post = _attach_images(cur, updated_post)
            return updated_post


# 게시글 삭제 (로그인 필요 + 작성자 본인만 가능)
@router.delete("/{post_id}")
def delete_post(post_id: int, x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    current_user = _get_current_user(x_user_id)
    from main import get_connection
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
def toggle_like(post_id: int, x_user_id: int | None = Header(default=None, alias="X-User-Id")):
    current_user = _get_current_user(x_user_id)
    from main import get_connection
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