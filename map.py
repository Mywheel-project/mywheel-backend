"""
네이버 지도(Naver Maps) 연동 관련 라우터.
main.py 는 이 라우터를 include_router 로 등록만 한다.

네이버 지도 JS SDK(Dynamic Map)는 Client ID만 있으면 되고, Client Secret은
필요 없다(Geocoding 등 서버 간 REST API를 쓸 때만 필요). 그래서 Client ID는
프론트가 지도 스크립트를 불러올 때 쓸 수 있도록 아래 /map/client-id 로 내려주고,
Client Secret은 .env 에만 보관한 채 아직 어디에서도 쓰지 않는다.
"""

import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

load_dotenv()

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/client-id")
def get_client_id():
    client_id = os.environ.get("NAVER_MAPS_CLIENT_ID")
    if not client_id:
        raise HTTPException(
            status_code=500, detail="NAVER_MAPS_CLIENT_ID 환경변수가 설정되어 있지 않습니다."
        )
    return {"client_id": client_id}


# 전체 34,000여 건을 한 번에 내려주면 브라우저가 감당하지 못하므로,
# 지도 화면에 실제로 보이는 영역(bounding box)만 조회하고 개수도 제한한다.
MAX_SHOP_RESULTS = 500


@router.get("/nearby")
def get_nearby_shops(
    sw_lat: float = Query(..., description="지도 화면 남서쪽 위도"),
    sw_lng: float = Query(..., description="지도 화면 남서쪽 경도"),
    ne_lat: float = Query(..., description="지도 화면 북동쪽 위도"),
    ne_lng: float = Query(..., description="지도 화면 북동쪽 경도"),
):
    if sw_lat > ne_lat or sw_lng > ne_lng:
        raise HTTPException(status_code=400, detail="잘못된 좌표 범위입니다.")

    # main.py 의 get_connection 을 재사용한다.
    # 함수 안에서 import 하는 이유: main.py 가 이 파일(map.py)을 import 하므로,
    # 모듈 최상단에서 서로를 import 하면 순환 import 오류가 발생한다.
    from main import get_connection
    import psycopg2.extras

    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, shop_type, road_address, lot_address,
                       latitude, longitude, phone, open_time, close_time
                FROM car_shops
                WHERE latitude BETWEEN %s AND %s
                  AND longitude BETWEEN %s AND %s
                LIMIT %s;
                """,
                (sw_lat, ne_lat, sw_lng, ne_lng, MAX_SHOP_RESULTS),
            )
            return cur.fetchall()
