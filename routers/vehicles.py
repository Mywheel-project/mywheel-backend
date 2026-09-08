"""
마이페이지 '내 차량' 카드 조회/등록 라우터.
유저당 차량은 1대만 관리한다 (vehicles.user_id UNIQUE, models.Vehicle 참고).
"""

import os
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import Vehicle

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "vehicles")
os.makedirs(STATIC_DIR, exist_ok=True)


def _require_user_id(x_user_id: Optional[int]) -> int:
    # users.py 와 동일하게, 로그인 시 프론트가 저장해둔 유저 id를
    # X-User-Id 헤더로 실어 보내는 방식으로 "나"를 식별한다.
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return x_user_id


def _serialize(vehicle: Vehicle) -> dict:
    return {
        "id": vehicle.id,
        "name": vehicle.name,
        "image_url": vehicle.image_url,
        "pcd": vehicle.pcd,
        "hole_count": vehicle.hole_count,
        "hub_bore": vehicle.hub_bore,
        "bolt_spec": vehicle.bolt_spec,
    }


@router.get("/me")
def get_my_vehicle(
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(x_user_id)
    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user_id).first()
    return _serialize(vehicle) if vehicle else None


@router.put("/me")
async def upsert_my_vehicle(
    name: str = Form(...),
    pcd: Optional[str] = Form(None),
    hole_count: Optional[str] = Form(None),
    hub_bore: Optional[str] = Form(None),
    bolt_spec: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(x_user_id)

    vehicle = db.query(Vehicle).filter(Vehicle.user_id == user_id).first()
    if vehicle is None:
        vehicle = Vehicle(user_id=user_id, name=name)
        db.add(vehicle)

    vehicle.name = name
    vehicle.pcd = pcd
    vehicle.hole_count = hole_count
    vehicle.hub_bore = hub_bore
    vehicle.bolt_spec = bolt_spec

    # 사진을 새로 올리지 않으면 기존 image_url을 그대로 유지한다.
    if image is not None:
        ext = os.path.splitext(image.filename or "")[1] or ".jpg"
        filename = f"{user_id}_{int(time.time() * 1000)}{ext}"
        file_path = os.path.join(STATIC_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(await image.read())
        vehicle.image_url = f"{BASE_URL}/static/vehicles/{filename}"

    db.commit()
    db.refresh(vehicle)

    return _serialize(vehicle)
