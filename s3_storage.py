"""
업로드 이미지를 S3에 저장/삭제하는 공용 모듈.

인증 정보는 코드나 .env에 두지 않고, EC2 인스턴스 역할(instanceRole)을 boto3가 자동으로 사용한다.
이미지 폴더는 버킷 정책으로 공개 읽기가 허용되어 있어, 반환된 URL을 그대로 DB에 저장해 쓴다.
"""

import mimetypes
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET_NAME = os.environ["S3_BUCKET_NAME"]
S3_REGION = os.environ["S3_REGION"]
S3_BASE_URL = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/"

_client = boto3.client("s3", region_name=S3_REGION)


def _image_content_type(filename: str) -> str:
    """이미지 확장자만 브라우저에 이미지로 표시되게 하고, 나머지는 다운로드 형식으로 둔다."""
    content_type, _ = mimetypes.guess_type(filename)
    if content_type and content_type.startswith("image/"):
        return content_type
    return "application/octet-stream"


def upload_image(prefix: str, filename: str, data: bytes) -> str:
    """이미지를 prefix 폴더에 올리고 공개 URL을 반환한다."""
    key = f"{prefix}/{filename}"
    _client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=_image_content_type(filename),
    )
    return f"{S3_BASE_URL}{key}"


def delete_image_by_url(url: str) -> None:
    """이 버킷의 이미지만 삭제한다. 삭제 실패는 기록만 하고 요청은 실패시키지 않는다."""
    if not url.startswith(S3_BASE_URL):
        return
    try:
        _client.delete_object(Bucket=S3_BUCKET_NAME, Key=url[len(S3_BASE_URL):])
    except (BotoCoreError, ClientError) as exc:
        print(f"[s3] 이미지 삭제 실패: {url}: {exc!r}")
