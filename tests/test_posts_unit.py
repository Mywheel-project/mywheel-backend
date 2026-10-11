# tests/test_posts_unit.py
import io

from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from routers import posts


def test_이미지_저장시_파일이_생기고_URL을_돌려줌(tmp_path, monkeypatch):
    # 실제 static/community 대신 pytest가 주는 임시 폴더에 저장되게 바꿔치기
    monkeypatch.setattr(posts, "STATIC_DIR", str(tmp_path))
    upload = UploadFile(filename="wheel.png", file=io.BytesIO(b"fake-image-bytes"))

    url = posts._save_image_locally(upload)

    saved = list(tmp_path.iterdir())
    assert len(saved) == 1
    assert saved[0].suffix == ".png"
    assert saved[0].read_bytes() == b"fake-image-bytes"
    assert url == f"http://localhost:8000/static/community/{saved[0].name}"


def test_같은_이름으로_두번_올려도_파일명이_겹치지_않음(tmp_path, monkeypatch):
    monkeypatch.setattr(posts, "STATIC_DIR", str(tmp_path))
    a = posts._save_image_locally(UploadFile(filename="a.jpg", file=io.BytesIO(b"1")))
    b = posts._save_image_locally(UploadFile(filename="a.jpg", file=io.BytesIO(b"2")))
    assert a != b


def test_확장자_없으면_jpg로_저장(tmp_path, monkeypatch):
    monkeypatch.setattr(posts, "STATIC_DIR", str(tmp_path))
    url = posts._save_image_locally(UploadFile(filename="noext", file=io.BytesIO(b"x")))
    assert url.endswith(".jpg")


# ---- 라우터 단위 테스트: main.py(=DB 연결)를 안 쓰고 posts 라우터만 붙인 작은 앱 ----
app = FastAPI()
app.include_router(posts.router)
client = TestClient(app)


def test_로그인_안하고_글쓰기하면_401():
    r = client.post("/api/posts", data={"title": "t", "content": "c"})
    assert r.status_code == 401


def test_잘못된_토큰으로_삭제하면_401():
    r = client.delete("/api/posts/1", headers={"Authorization": "Bearer fake.token.value"})
    assert r.status_code == 401


# 댓글 라우터도 같은 방식으로: 로그인 없이 댓글 쓰면 401
from routers import comments

comment_app = FastAPI()
comment_app.include_router(comments.router)
comment_client = TestClient(comment_app)


def test_로그인_안하고_댓글쓰면_401():
    r = comment_client.post("/api/posts/1/comments", json={"content": "댓글"})
    assert r.status_code == 401