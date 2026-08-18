"""
인증(회원가입) 관련 라우터.
main.py 는 이 라우터를 include_router 로 등록만 하고,
실제 요청 검증 / 비밀번호 해싱 / DB 저장 로직은 모두 여기서 처리한다.
"""

import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

# 이 라우터의 모든 엔드포인트는 자동으로 "/auth" 접두사가 붙는다.
# 따라서 아래 signup 함수의 "/signup" 은 실제로는 "/auth/signup" 이 된다.
router = APIRouter(prefix="/auth", tags=["auth"])

# 아직 실제 프로필 이미지 업로드 기능이 없어서, 가입 시 모든 유저에게
# 동일한 더미 프로필 이미지 URL을 저장해둔다.
DUMMY_PROFILE_IMAGE_URL = "https://placehold.co/200x200/9E9E9E/FFFFFF?text=User"


class SignupRequest(BaseModel):
    """회원가입 요청 바디. 프론트엔드 SignupModal 의 입력값과 1:1로 대응된다."""

    email: EmailStr
    password: str = Field(min_length=1, description="평문 비밀번호. 서버에서 해시 후 저장한다.")
    nickname: str = Field(min_length=1, max_length=50)


class SignupResponse(BaseModel):
    """회원가입 성공 응답. 비밀번호(해시 포함)는 절대 응답에 담지 않는다."""

    id: int
    email: EmailStr
    nickname: str
    profile_image: str | None = None


@router.post("/signup", response_model=SignupResponse, status_code=201)
def signup(payload: SignupRequest):
    # main.py 의 get_connection 을 재사용한다.
    # 함수 안에서 import 하는 이유: main.py 가 이 파일(auth.py)을 import 하므로,
    # 모듈 최상단에서 서로를 import 하면 순환 import 오류가 발생한다.
    from main import get_connection

    # bcrypt 는 비밀번호를 그대로 저장하지 않고 단방향 해시로 변환해 저장한다.
    # gensalt() 가 매번 다른 salt 를 생성하므로 같은 비밀번호라도 해시값이 달라진다.
    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 이메일 중복 가입 방지 (users.email 은 UNIQUE 이지만, 사용자에게
            # 더 친절한 에러 메시지를 주기 위해 미리 조회한다).
            cur.execute("SELECT id FROM users WHERE email = %s;", (payload.email,))
            if cur.fetchone() is not None:
                raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

            # provider 는 자체(local) 회원가입이므로 'local' 로 고정 저장한다.
            # created_at / updated_at 은 DB 기본값(now())을 그대로 사용한다.
            cur.execute(
                """
                INSERT INTO users (email, password_hash, nickname, profile_image, provider)
                VALUES (%s, %s, %s, %s, 'local')
                RETURNING id, email, nickname, profile_image;
                """,
                (payload.email, password_hash, payload.nickname, DUMMY_PROFILE_IMAGE_URL),
            )
            new_id, new_email, new_nickname, new_profile_image = cur.fetchone()
            conn.commit()

    return SignupResponse(
        id=new_id, email=new_email, nickname=new_nickname, profile_image=new_profile_image
    )


class LoginRequest(BaseModel):
    """로그인 요청 바디. 프론트엔드 LoginModal 의 입력값과 1:1로 대응된다."""

    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    """로그인 성공 응답. 프론트엔드는 이 값을 localStorage 에 저장해 로그인 상태를 유지한다."""

    id: int
    email: EmailStr
    nickname: str
    profile_image: str | None = None


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    from main import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, nickname, password_hash, profile_image FROM users WHERE email = %s;",
                (payload.email,),
            )
            row = cur.fetchone()

    # 이메일이 없거나 비밀번호가 틀린 경우 둘 다 같은 메시지로 응답한다.
    # (둘 중 어떤 것이 틀렸는지 알려주면 공격자가 가입된 이메일을 추측할 수 있다)
    invalid_credentials = HTTPException(
        status_code=401, detail="이메일 또는 비밀번호가 일치하지 않습니다."
    )
    if row is None:
        raise invalid_credentials

    user_id, email, nickname, password_hash, profile_image = row
    if not password_hash or not bcrypt.checkpw(
        payload.password.encode("utf-8"), password_hash.encode("utf-8")
    ):
        raise invalid_credentials

    return LoginResponse(id=user_id, email=email, nickname=nickname, profile_image=profile_image)
