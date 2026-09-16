import os
import io
import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Optional
from PIL import Image
from fastapi import APIRouter, File, Form, Header, UploadFile, HTTPException, Query, Depends, Request
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from database import get_db
from models import AdviceLog, CustomSynthesisLog

# 환경 변수 로드
load_dotenv()

# 라우터 및 API 클라이언트 초기화
router = APIRouter()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 전역 상수 / 경로 / 기본 URL 설정
BASE_URL = os.getenv("BASE_URL")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "results")
os.makedirs(STATIC_DIR, exist_ok=True)

# KST(한국 표준시) 및 주간 5회 제한 설정
KST = timezone(timedelta(hours=9))

# 이 값으로 리밋값 조정
WEEKLY_LIMIT = 999


def get_current_week_start_utc() -> datetime:
    """현재 주차의 시작 시각 (월요일 00:00:00 KST)을 UTC naive datetime으로 반환"""
    now_kst = datetime.now(KST)
    start_of_week_date = now_kst.date() - timedelta(days=now_kst.weekday())
    start_of_week_kst = datetime.combine(start_of_week_date, dtime.min, tzinfo=KST)
    return start_of_week_kst.astimezone(timezone.utc).replace(tzinfo=None)


def resolve_client_id(request: Request, x_client_id: Optional[str] = None) -> str:
    """클라이언트 고유 식별자(프론트 생성 UUID 또는 IP) 반환"""
    if x_client_id and x_client_id.strip():
        return x_client_id.strip()
    client_ip = request.client.host if (request and request.client) else "unknown"
    return f"ip_{client_ip}"


def get_feature_usage_count(
    db: Session,
    feature_type: str,
    user_id: Optional[int],
    client_id: Optional[str],
) -> int:
    """현재 주차(월요일 00:00 KST 이후) 기준 기능별 사용 횟수 조회"""
    week_start = get_current_week_start_utc()

    if feature_type == "tuning":
        model = CustomSynthesisLog
        base_query = db.query(func.count(model.id)).filter(model.created_at >= week_start)
    elif feature_type == "recommend":
        model = AdviceLog
        base_query = db.query(func.count(model.id)).filter(
            model.query_type == "RECOMMEND",
            model.created_at >= week_start
        )
    elif feature_type == "search":
        model = AdviceLog
        base_query = db.query(func.count(model.id)).filter(
            model.query_type == "SEARCH",
            model.created_at >= week_start
        )
    else:
        return 0

    if user_id and client_id:
        user_cond = or_(
            model.user_id == user_id,
            and_(model.user_id.is_(None), model.client_id == client_id)
        )
    elif user_id:
        user_cond = (model.user_id == user_id)
    elif client_id:
        user_cond = (model.client_id == client_id)
    else:
        return 0

    return base_query.filter(user_cond).scalar() or 0


# ----------------------------------------------------
# 0. 커스텀 기능 주간 잔여 횟수 조회: GET /api/v1/custom/limits
# ----------------------------------------------------
@router.get("/custom/limits", tags=["Custom"])
def get_custom_feature_limits(
    request: Request,
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id"),
    db: Session = Depends(get_db),
):
    client_id = resolve_client_id(request, x_client_id)

    tuning_used = get_feature_usage_count(db, "tuning", x_user_id, client_id)
    recommend_used = get_feature_usage_count(db, "recommend", x_user_id, client_id)
    search_used = get_feature_usage_count(db, "search", x_user_id, client_id)

    return {
        "weekly_limit": WEEKLY_LIMIT,
        "tuning": {
            "used": tuning_used,
            "remaining": max(0, WEEKLY_LIMIT - tuning_used),
            "max": WEEKLY_LIMIT,
        },
        "recommend": {
            "used": recommend_used,
            "remaining": max(0, WEEKLY_LIMIT - recommend_used),
            "max": WEEKLY_LIMIT,
        },
        "search": {
            "used": search_used,
            "remaining": max(0, WEEKLY_LIMIT - search_used),
            "max": WEEKLY_LIMIT,
        },
    }


# Gemini 2.5 Flash Image가 지원하는 종횡비 목록 (3.1 사용하면 이거 안써도 되는지 테스트 해봐야함) 
SUPPORTED_ASPECT_RATIOS = {
    "1:1": 1 / 1,
    "2:3": 2 / 3,
    "3:2": 3 / 2,
    "3:4": 3 / 4,
    "4:3": 4 / 3,
    "4:5": 4 / 5,
    "5:4": 5 / 4,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "21:9": 21 / 9,
}


def closest_supported_aspect_ratio(width: int, height: int) -> str:
    """원본 이미지 비율과 가장 가까운 Gemini 지원 비율을 반환"""
    target = width / height
    return min(SUPPORTED_ASPECT_RATIOS, key=lambda k: abs(SUPPORTED_ASPECT_RATIOS[k] - target))


# ----------------------------------------------------
# 1. 휠 커스텀 합성 요청: POST /api/v1/custom/synthesize
# ----------------------------------------------------
@router.post("/custom/synthesize", tags=["Custom"])
async def synthesize_custom_wheel(
    request: Request,
    original_vehicle_image: UploadFile = File(..., description="사용자가 업로드한 원본 차량 사진 (필수)"),
    uploaded_wheel_image: Optional[UploadFile] = File(None, description="사용자가 직접 업로드한 휠 사진"),
    selected_asset_id: Optional[str] = Form(None, description="기본 라이브러리에서 선택한 휠 ID"),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id"),
    db: Session = Depends(get_db),
):
    client_id = resolve_client_id(request, x_client_id)
    used_count = get_feature_usage_count(db, "tuning", x_user_id, client_id)
    if used_count >= WEEKLY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="이번 주 휠 튜닝 이용 한도(5회)를 모두 소진했습니다. 다음 주 월요일 00:00에 다시 충전됩니다."
        )

    if not uploaded_wheel_image and not selected_asset_id:
        raise HTTPException(
            status_code=400,
            detail="uploaded_wheel_image 또는 selected_asset_id 중 하나는 필수입니다."
        )

    try:
        # 1) 원본 차량 이미지 로드
        vehicle_bytes = await original_vehicle_image.read()
        vehicle_pil = Image.open(io.BytesIO(vehicle_bytes))

        # 원본 비율에 가장 가까운 지원 비율 계산
        target_aspect_ratio = closest_supported_aspect_ratio(*vehicle_pil.size)

        # 2) 합성용 프롬프트 + 입력 이미지 구성
        if uploaded_wheel_image:
            wheel_bytes = await uploaded_wheel_image.read()
            wheel_pil = Image.open(io.BytesIO(wheel_bytes))

            edit_prompt = (
                "Image 1 is a car. Image 2 is a wheel rim. "
                "Replace the car's wheels with the exact wheel design shown in Image 2, "
                "keeping the car's color, body, angle, background, lighting, and original framing/aspect ratio "
                "exactly as in Image 1. Photorealistic result, perfect fitment on all visible wheels."
            )
            contents = [edit_prompt, vehicle_pil, wheel_pil]
        else:
            edit_prompt = (
                f"Image 1 is a car. Replace its wheels with '{selected_asset_id}' style wheels, "
                "keeping the car's exact color, body, angle, background, lighting, and original framing/aspect ratio. "
                "Photorealistic result, perfect fitment."
            )
            contents = [edit_prompt, vehicle_pil]

        # 3) Gemini 2.5 Flash Image(나노바나나)로 직접 합성
        image_response = client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=target_aspect_ratio,
                ),
            ),
        )

        # 4) 생성된 이미지 파트에서 바이트 추출
        generated_bytes = None
        for part in image_response.parts:
            if part.inline_data is not None:
                generated_bytes = part.inline_data.data
                break

        if generated_bytes is None:
            raise HTTPException(status_code=500, detail="이미지 합성 결과를 받지 못했습니다.")

        # 5) 로컬 결과 파일 저장
        result_id = int(time.time() * 1000)
        output_filename = f"result_{result_id}.jpg"
        output_path = os.path.join(STATIC_DIR, output_filename)

        with open(output_path, "wb") as f:
            f.write(generated_bytes)

        result_image_url = f"{BASE_URL}/static/results/{output_filename}"

        # 6) DB에 저장
        asset_info = selected_asset_id if not uploaded_wheel_image else "UPLOADED_IMAGE"
        synthesis_log = CustomSynthesisLog(
            user_id=x_user_id,
            client_id=client_id,
            selected_asset_id=asset_info,
            result_image_url=result_image_url
        )
        db.add(synthesis_log)
        db.commit()
        db.refresh(synthesis_log)

        return {
            "result_id": synthesis_log.id,
            "result_image_url": synthesis_log.result_image_url,
            "remaining": max(0, WEEKLY_LIMIT - (used_count + 1)),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"합성 처리 오류: {str(e)}")


# ----------------------------------------------------
# 1-1. 내 합성 갤러리 조회: GET /api/v1/custom/gallery
# ----------------------------------------------------
@router.get("/custom/gallery", tags=["Custom"])
def get_my_gallery(
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    logs = (
        db.query(CustomSynthesisLog)
        .filter(CustomSynthesisLog.user_id == x_user_id)
        .order_by(CustomSynthesisLog.created_at.desc())
        .all()
    )

    return [
        {
            "id": log.id,
            "image_url": log.result_image_url,
            "created_at": log.created_at,
        }
        for log in logs
    ]


# ----------------------------------------------------
# 2. 차량 휠/타이어 제원 추천 API: POST /api/v1/recommend/vehicle
# ----------------------------------------------------
class VehicleRecommendBody(BaseModel):
    vehicle_model: str = Field(..., example="현대 아반떼 CN7", description="사용자가 입력한 차량 모델명")

@router.post("/recommend/vehicle", tags=["Recommend"])
async def recommend_vehicle_specs(
    request: Request,
    body: VehicleRecommendBody,
    id: Optional[int] = Query(None, description="사용자 정보 id (BIGSERIAL, 선택사항)"),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id"),
    db: Session = Depends(get_db),
):
    effective_user_id = x_user_id or id
    client_id = resolve_client_id(request, x_client_id)

    used_count = get_feature_usage_count(db, "recommend", effective_user_id, client_id)
    if used_count >= WEEKLY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="이번 주 차량 제원 추천 이용 한도(5회)를 모두 소진했습니다. 다음 주 월요일 00:00에 다시 충전됩니다."
        )

    prompt = (
    f"차종: {body.vehicle_model}\n\n"
    "너는 자동차 휠/타이어 피팅 전문 튜닝 엔지니어다. "
    "위 차종의 순정 규격(PCD, 허브 사이즈, 홀 수)과 함께 간섭 없이 장착 가능한 추천 휠 인치/옵셋(ET)/림폭(J), "
    "작성 규칙:\n"
    "- 전체 500자 이내로 간결하게\n"
    "- 이모지, 인사말, 감탄사 사용 금지\n"
    "- 헤더(#)와 구분선(---) 사용 금지, 굵은 글씨는 핵심 수치에만 최소한으로\n"
    "- 표 1개 + 짧은 문장으로만 구성"
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        # DB에 저장
        advice_log = AdviceLog(
            user_id=effective_user_id,
            client_id=client_id,
            query_type="RECOMMEND",
            user_query=body.vehicle_model,
            gemini_response=response.text
        )
        db.add(advice_log)
        db.commit()
        db.refresh(advice_log)

        return {
            "advice_id": advice_log.id,
            "gemini_response": advice_log.gemini_response,
            "remaining": max(0, WEEKLY_LIMIT - (used_count + 1)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 분석 중 오류 발생: {str(e)}")


# ----------------------------------------------------
# 3. 휠 이름으로 제원 검색 API: POST /api/v1/search/wheel
# ----------------------------------------------------
class WheelSearchBody(BaseModel):
    wheel_name: str = Field(..., example="BBS LM", description="검색할 휠 제품명")
    vehicle_model: Optional[str] = Field(None, example="현대 아반떼 CN7", description="호환성을 함께 확인할 차량 모델명")

@router.post("/search/wheel", tags=["Search"])
async def search_wheel_spec(
    request: Request,
    body: WheelSearchBody,
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    x_client_id: Optional[str] = Header(default=None, alias="X-Client-Id"),
    db: Session = Depends(get_db),
):
    client_id = resolve_client_id(request, x_client_id)

    used_count = get_feature_usage_count(db, "search", x_user_id, client_id)
    if used_count >= WEEKLY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="이번 주 휠 제원 검색 이용 한도(5회)를 모두 소진했습니다. 다음 주 월요일 00:00에 다시 충전됩니다."
        )

    style_rules = (
        "\n\n작성 규칙:\n"
        "- 전체 500자 이내로 간결하게\n"
        "- 인사말, 감탄사, 이모지, 결론 요약 문단 사용 금지\n"
        "- 헤더(#)와 구분선(---) 사용 금지\n"
        "- 굵은 글씨는 핵심 수치(PCD, 옵셋, 인치)에만 최소한으로\n"
        "- 표 1개 + 짧은 문장 위주로 구성"
    )

    if body.vehicle_model:
        prompt = (
            f"휠 제품명: {body.wheel_name}\n"
            f"대상 차량: {body.vehicle_model}\n\n"
            f"1. {body.wheel_name}의 제조사, 제조 공법, PCD/사이즈 라인업을 요약해줘.\n"
            f"2. 해당 휠이 {body.vehicle_model}에 PCD, 옵셋, 휀더 간섭 없이 장착 가능한지 진단해줘."
            + style_rules
        )
        query_text = f"휠: {body.wheel_name}, 차량: {body.vehicle_model}"
    else:
        prompt = (
            f"휠 제품명: {body.wheel_name}\n\n"
            f"{body.wheel_name}의 제조사, 주요 출시 인치 및 PCD, 림폭/옵셋 범위, 제조 공법을 요약해줘."
            + style_rules
        )
        query_text = f"휠: {body.wheel_name}"

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )

        # DB에 저장
        advice_log = AdviceLog(
            user_id=x_user_id,
            client_id=client_id,
            query_type="SEARCH",
            user_query=query_text,
            gemini_response=response.text
        )
        db.add(advice_log)
        db.commit()
        db.refresh(advice_log)

        return {
            "advice_id": advice_log.id,
            "gemini_response": advice_log.gemini_response,
            "remaining": max(0, WEEKLY_LIMIT - (used_count + 1)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제원 검색 중 오류 발생: {str(e)}")