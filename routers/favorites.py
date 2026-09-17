from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import get_db
from models import UserWheelFavorite

router = APIRouter(prefix="/favorites", tags=["Favorites"])


class ToggleFavoriteRequest(BaseModel):
    user_id: Optional[int] = Field(None, description="사용자 ID (헤더 X-User-Id 또는 Body로 전달)")
    wheel_id: int = Field(..., description="휠 에셋 ID")


class ToggleFavoriteResponse(BaseModel):
    user_id: int
    wheel_id: int
    is_favorite: bool
    favorite_wheel_ids: list[int]


class FavoritesListResponse(BaseModel):
    user_id: int
    favorite_wheel_ids: list[int]


class SyncFavoritesRequest(BaseModel):
    user_id: Optional[int] = Field(None, description="사용자 ID (헤더 X-User-Id 또는 Body로 전달)")
    favorite_wheel_ids: list[int] = Field(..., description="동기화할 휠 ID 리스트")


def resolve_user_id(user_id_param: Optional[int], x_user_id: Optional[int]) -> int:
    resolved = user_id_param or x_user_id
    if not resolved:
        raise HTTPException(status_code=400, detail="user_id가 필요합니다. 쿼리 파라미터나 X-User-Id 헤더를 확인해주세요.")
    return resolved


@router.get("/wheels", response_model=FavoritesListResponse, summary="사용자의 휠 에셋 즐겨찾기 목록 조회")
def get_user_wheel_favorites(
    user_id: Optional[int] = Query(None, description="조회할 사용자 ID"),
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    target_user_id = resolve_user_id(user_id, x_user_id)
    records = (
        db.query(UserWheelFavorite.wheel_id)
        .filter(UserWheelFavorite.user_id == target_user_id)
        .order_by(UserWheelFavorite.created_at.asc())
        .all()
    )
    favorite_wheel_ids = [r[0] for r in records]
    return FavoritesListResponse(user_id=target_user_id, favorite_wheel_ids=favorite_wheel_ids)


@router.post("/wheels/toggle", response_model=ToggleFavoriteResponse, summary="휠 에셋 즐겨찾기 토글 (추가/해제)")
def toggle_wheel_favorite(
    payload: ToggleFavoriteRequest,
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    target_user_id = resolve_user_id(payload.user_id, x_user_id)

    existing = (
        db.query(UserWheelFavorite)
        .filter(
            UserWheelFavorite.user_id == target_user_id,
            UserWheelFavorite.wheel_id == payload.wheel_id,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        is_favorite = False
    else:
        new_fav = UserWheelFavorite(user_id=target_user_id, wheel_id=payload.wheel_id)
        db.add(new_fav)
        db.commit()
        is_favorite = True

    records = (
        db.query(UserWheelFavorite.wheel_id)
        .filter(UserWheelFavorite.user_id == target_user_id)
        .order_by(UserWheelFavorite.created_at.asc())
        .all()
    )
    favorite_wheel_ids = [r[0] for r in records]

    return ToggleFavoriteResponse(
        user_id=target_user_id,
        wheel_id=payload.wheel_id,
        is_favorite=is_favorite,
        favorite_wheel_ids=favorite_wheel_ids,
    )


@router.post("/wheels/sync", response_model=FavoritesListResponse, summary="로컬 즐겨찾기 목록과 DB 일괄 병합 동기화")
def sync_wheel_favorites(
    payload: SyncFavoritesRequest,
    x_user_id: Optional[int] = Header(None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    target_user_id = resolve_user_id(payload.user_id, x_user_id)

    existing_ids = {
        r[0]
        for r in db.query(UserWheelFavorite.wheel_id)
        .filter(UserWheelFavorite.user_id == target_user_id)
        .all()
    }

    for wheel_id in payload.favorite_wheel_ids:
        if wheel_id not in existing_ids:
            db.add(UserWheelFavorite(user_id=target_user_id, wheel_id=wheel_id))

    db.commit()

    records = (
        db.query(UserWheelFavorite.wheel_id)
        .filter(UserWheelFavorite.user_id == target_user_id)
        .order_by(UserWheelFavorite.created_at.asc())
        .all()
    )
    favorite_wheel_ids = [r[0] for r in records]

    return FavoritesListResponse(user_id=target_user_id, favorite_wheel_ids=favorite_wheel_ids)
