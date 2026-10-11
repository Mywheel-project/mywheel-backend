# tests/test_custom_utils.py
from datetime import datetime
from types import SimpleNamespace

import pytest

from routers import custom
from routers.custom import closest_supported_aspect_ratio, resolve_client_id


@pytest.mark.parametrize("w, h, expected", [
    (1000, 1000, "1:1"),
    (1920, 1080, "16:9"),
    (1080, 1920, "9:16"),
    (4000, 3000, "4:3"),
    (2560, 1080, "21:9"),
])
def test_가장_가까운_종횡비(w, h, expected):
    assert closest_supported_aspect_ratio(w, h) == expected


def test_client_id_헤더가_있으면_그대로_사용():
    assert resolve_client_id(None, "  client_abc  ") == "client_abc"


def test_client_id_없으면_IP로_대체():
    fake_request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"))
    assert resolve_client_id(fake_request, None) == "ip_1.2.3.4"


def test_주간_시작은_월요일_0시_KST(monkeypatch):
    # 2026-10-08(목) 15:00 KST 라고 "시간을 고정"
    fixed_now = datetime(2026, 10, 8, 15, 0, tzinfo=custom.KST)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now

    monkeypatch.setattr(custom, "datetime", FakeDatetime)
    # 월요일 10/5 00:00 KST == 10/4 15:00 UTC
    assert custom.get_current_week_start_utc() == datetime(2026, 10, 4, 15, 0)