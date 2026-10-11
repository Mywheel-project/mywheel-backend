# tests/conftest.py
# 앱 코드를 import 하기 "전에" 테스트용 환경변수를 넣어둔다.
# (jwt_auth.py는 JWT_SECRET_KEY가 없으면 import 순간 에러, database.py는 DATABASE_URL이 None이면 에러)
# load_dotenv()는 이미 있는 환경변수를 덮어쓰지 않으므로 .env보다 여기 값이 우선한다.
import os
import sys

os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5999/not_used"  # 단위 테스트는 실제로 접속 안 함
os.environ["GEMINI_API_KEY"] = "fake-key"

# 프로젝트 루트(mywheel-backend-new)를 import 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))