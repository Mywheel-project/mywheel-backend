from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Docker DB 접속 정보 (계정:mywheel, 비번:mywheel, 포트:5432, DB:mywheel)
SQLALCHEMY_DATABASE_URL = "postgresql://mywheel:mywheel@localhost:5432/mywheel"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# DB 세션 획득용 의존성 함수
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()