"""Gmail SMTP로 회원가입 인증 코드 메일을 보내는 유틸리티.

Gmail은 일반 로그인 비밀번호로 SMTP 인증을 받아주지 않으므로, 발신 계정에
2단계 인증을 켠 뒤 발급한 "앱 비밀번호"를 GMAIL_APP_PASSWORD 로 써야 한다.
"""

import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def send_verification_email(to_email: str, code: str) -> None:
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD 환경변수가 설정되지 않았습니다.")

    message = MIMEText(
        f"MyWheel 회원가입 인증 코드입니다.\n\n인증 코드: {code}\n\n10분 안에 입력해주세요."
    )
    message["Subject"] = "[MyWheel] 이메일 인증 코드"
    message["From"] = GMAIL_ADDRESS
    message["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_email], message.as_string())
