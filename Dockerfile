FROM python:3.12-slim

WORKDIR /app

# requirements.txt만 먼저 복사 → 코드만 바뀌면 이 레이어(pip install)는 캐시돼서 재빌드 안 함
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 개발 모드: 실제 코드는 docker-compose-back.yml에서 볼륨마운트로 덮어씌움
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
