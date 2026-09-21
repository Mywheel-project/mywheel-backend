"""
인증(회원가입) 관련 라우터.
main.py 는 이 라우터를 include_router 로 등록만 하고,
실제 요청 검증 / 비밀번호 해싱 / DB 저장 로직은 모두 여기서 처리한다.
"""

import os
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel, EmailStr, Field

from mailer import send_verification_email

# 이 라우터의 모든 엔드포인트는 자동으로 "/auth" 접두사가 붙는다.
# 따라서 아래 signup 함수의 "/signup" 은 실제로는 "/auth/signup" 이 된다.
router = APIRouter(prefix="/auth", tags=["auth"])

# 아직 실제 프로필 이미지 업로드 기능이 없어서, 가입 시 모든 유저에게
# 동일한 더미 프로필 이미지 URL을 저장해둔다.
DUMMY_PROFILE_IMAGE_URL = "https://placehold.co/200x200/9E9E9E/FFFFFF?text=User"

# 이메일 인증 코드 관련 정책값.
CODE_EXPIRE_MINUTES = 10  # 코드 유효 시간
RESEND_COOLDOWN_SECONDS = 60  # 재전송 최소 간격 (메일 스팸 발송 방지)
MAX_CODE_ATTEMPTS = 5  # 틀린 코드 허용 횟수 (브루트포스 방지)


class SignupRequest(BaseModel):
    """회원가입 요청 바디. 프론트엔드 SignupModal 의 입력값과 1:1로 대응된다."""

    email: EmailStr
    password: str = Field(min_length=1, description="평문 비밀번호. 서버에서 해시 후 저장한다.")
    nickname: str = Field(min_length=1, max_length=50)


class SignupResponse(BaseModel):
    """계정 생성 성공 응답(이메일 인증 완료 시점). 비밀번호(해시 포함)는 절대 응답에 담지 않는다."""

    id: int
    email: EmailStr
    nickname: str
    profile_image: str | None = None


class SignupPendingResponse(BaseModel):
    """인증 코드 발송 완료 응답. 이 시점에는 아직 계정이 생성되지 않았다."""

    email: EmailStr
    message: str = "인증 코드를 이메일로 보냈습니다."


@router.post("/signup", response_model=SignupPendingResponse)
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
    # secrets.randbelow 는 암호학적으로 안전한 난수를 생성한다 (random 모듈 대신 사용).
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=CODE_EXPIRE_MINUTES)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 이미 인증까지 끝난 이메일이면 여기서 막는다 (실제 중복 가입 방지).
            cur.execute("SELECT id FROM users WHERE email = %s;", (payload.email,))
            if cur.fetchone() is not None:
                raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

            # 같은 이메일로 너무 자주 재요청하면 메일 스팸이 되므로 최소 간격을 둔다.
            cur.execute(
                "SELECT last_sent_at FROM pending_signups WHERE email = %s;",
                (payload.email,),
            )
            row = cur.fetchone()
            if row is not None:
                elapsed = (now - row[0]).total_seconds()
                if elapsed < RESEND_COOLDOWN_SECONDS:
                    wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
                    raise HTTPException(
                        status_code=429, detail=f"{wait}초 후 다시 시도해주세요."
                    )

            # 같은 이메일로 재요청한 경우 새 row 를 만들지 않고 코드만 갱신한다
            # (인증 안 된 row 가 방치되어 쌓이는 걸 막는다).
            cur.execute(
                """
                INSERT INTO pending_signups
                    (email, password_hash, nickname, code, expires_at, attempt_count, last_sent_at)
                VALUES (%s, %s, %s, %s, %s, 0, %s)
                ON CONFLICT (email) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    nickname = EXCLUDED.nickname,
                    code = EXCLUDED.code,
                    expires_at = EXCLUDED.expires_at,
                    attempt_count = 0,
                    last_sent_at = EXCLUDED.last_sent_at;
                """,
                (payload.email, password_hash, payload.nickname, code, expires_at, now),
            )
            conn.commit()

    send_verification_email(payload.email, code)

    return SignupPendingResponse(email=payload.email)


class VerifyCodeRequest(BaseModel):
    """이메일 인증 코드 확인 요청 바디. 이 요청이 성공해야 실제 계정이 생성된다."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


@router.post("/verify-code", response_model=SignupResponse, status_code=201)
def verify_code(payload: VerifyCodeRequest):
    from main import get_connection

    now = datetime.utcnow()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT password_hash, nickname, code, expires_at, attempt_count
                FROM pending_signups WHERE email = %s;
                """,
                (payload.email,),
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=400, detail="인증 요청을 먼저 진행해주세요.")

            password_hash, nickname, correct_code, expires_at, attempt_count = row

            if now > expires_at:
                cur.execute("DELETE FROM pending_signups WHERE email = %s;", (payload.email,))
                conn.commit()
                raise HTTPException(
                    status_code=400, detail="인증 코드가 만료되었습니다. 다시 가입을 요청해주세요."
                )

            if attempt_count >= MAX_CODE_ATTEMPTS:
                cur.execute("DELETE FROM pending_signups WHERE email = %s;", (payload.email,))
                conn.commit()
                raise HTTPException(
                    status_code=400, detail="인증 시도 횟수를 초과했습니다. 다시 가입을 요청해주세요."
                )

            if payload.code != correct_code:
                cur.execute(
                    "UPDATE pending_signups SET attempt_count = attempt_count + 1 WHERE email = %s;",
                    (payload.email,),
                )
                conn.commit()
                raise HTTPException(status_code=401, detail="인증 코드가 일치하지 않습니다.")

            # 코드가 맞으면 이메일 소유가 확인된 것 -> 이 시점에 처음으로 실제 계정을 만든다.
            cur.execute("SELECT id FROM users WHERE email = %s;", (payload.email,))
            if cur.fetchone() is not None:
                cur.execute("DELETE FROM pending_signups WHERE email = %s;", (payload.email,))
                conn.commit()
                raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")

            cur.execute(
                """
                INSERT INTO users (email, password_hash, nickname, profile_image, provider)
                VALUES (%s, %s, %s, %s, 'local')
                RETURNING id, email, nickname, profile_image;
                """,
                (payload.email, password_hash, nickname, DUMMY_PROFILE_IMAGE_URL),
            )
            new_id, new_email, new_nickname, new_profile_image = cur.fetchone()

            cur.execute("DELETE FROM pending_signups WHERE email = %s;", (payload.email,))
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


class GoogleLoginRequest(BaseModel):
    """구글 로그인 요청 바디. 프론트에서 Google Identity Services 로 받은 ID 토큰(JWT)을 그대로 담는다."""

    credential: str = Field(min_length=1)


@router.post("/google", response_model=LoginResponse)
def google_login(payload: GoogleLoginRequest):
    from main import get_connection

    # verify_oauth2_token 이 서명/만료/audience(GOOGLE_CLIENT_ID)를 모두 검증해준다.
    # 검증에 실패하면 ValueError 를 던진다.
    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.credential, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
        )
    except ValueError as exc:
        print(f"[auth/google] verify_oauth2_token failed: {exc!r}")  # TEMP DEBUG
        raise HTTPException(status_code=401, detail="유효하지 않은 구글 인증 정보입니다.")

    email = idinfo["email"]
    nickname = idinfo.get("name") or email.split("@")[0]
    profile_image = idinfo.get("picture")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, nickname, profile_image, provider FROM users WHERE email = %s;",
                (email,),
            )
            row = cur.fetchone()

            # 이미 이메일/비밀번호로 가입된 계정이면 자동으로 연동하지 않고 막는다.
            # (구글 계정 소유자가 아닌 사람이 같은 이메일로 남의 로컬 계정에 접근하는 것을 방지)
            if row is not None and row[4] != "google":
                raise HTTPException(
                    status_code=409,
                    detail="이미 이메일/비밀번호로 가입된 계정입니다. 이메일과 비밀번호로 로그인해주세요.",
                )

            if row is None:
                # 처음 구글로 로그인하는 사용자 -> 자동 가입. password_hash 는 없다(NULL).
                cur.execute(
                    """
                    INSERT INTO users (email, nickname, profile_image, provider)
                    VALUES (%s, %s, %s, 'google')
                    RETURNING id, email, nickname, profile_image;
                    """,
                    (email, nickname, profile_image),
                )
                row = cur.fetchone()
                conn.commit()
            else:
                row = row[:4]

    user_id, user_email, user_nickname, user_profile_image = row
    return LoginResponse(
        id=user_id, email=user_email, nickname=user_nickname, profile_image=user_profile_image
    )
