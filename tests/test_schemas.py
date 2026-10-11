# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from schemas import PostCreate, PostResponse


def test_PostCreate_정상():
    p = PostCreate(title="휠 추천", content="본문")
    assert p.title == "휠 추천"


def test_PostCreate_제목_없으면_에러():
    with pytest.raises(ValidationError):
        PostCreate(content="제목 없음")


def test_PostResponse_기본값():
    r = PostResponse(id=1, title="t", content="c", author="성윤",
                     created_at="2026-10-08T12:00:00")
    assert r.likes_count == 0
    assert r.images == []
    assert r.liked_by_me is False