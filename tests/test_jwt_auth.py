# tests/test_jwt_auth.py
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

import jwt_auth
from jwt_auth import create_access_token, _decode_user_id, get_current_user_id


def test_발급한_토큰을_다시_해독하면_같은_유저id():
    token = create_access_token(42)
    assert _decode_user_id(f"Bearer {token}") == 42


@pytest.mark.parametrize("header", [
    None,                    # 헤더 없음
    "",                      # 빈 문자열
    "Bearer",                # 토큰 없음
    "Basic abc.def.ghi",     # Bearer가 아님
    "Bearer 이상한토큰",      # 형식 깨진 토큰
])
def test_잘못된_헤더는_None(header):
    assert _decode_user_id(header) is None


def test_다른_키로_서명된_토큰은_거부():
    fake = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        "hacker-key", algorithm="HS256",
    )
    assert _decode_user_id(f"Bearer {fake}") is None


def test_만료된_토큰은_거부():
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        jwt_auth.JWT_SECRET_KEY, algorithm="HS256",
    )
    assert _decode_user_id(f"Bearer {expired}") is None


def test_exp_없는_영구토큰은_거부():
    no_exp = jwt.encode({"sub": "1"}, jwt_auth.JWT_SECRET_KEY, algorithm="HS256")
    assert _decode_user_id(f"Bearer {no_exp}") is None


def test_로그인_필수_API는_토큰없으면_401():
    with pytest.raises(HTTPException) as e:
        get_current_user_id(None)
    assert e.value.status_code == 401