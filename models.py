from sqlalchemy import Column, BigInteger, String, Text, TIMESTAMP, ForeignKey, Table, func
from database import Base

# users 테이블은 SQLAlchemy 모델이 아니라 db/schema.sql 로 수동 생성되므로 Base.metadata에
# 등록되어 있지 않다. Vehicle.user_id 가 "users.id"를 FK로 참조하려면 create_all() 이 그
# 이름의 Table을 metadata에서 찾을 수 있어야 하므로, id 컬럼만 가진 프록시 Table을 등록해둔다.
# 실제 users 테이블은 이미 DB에 존재하므로 create_all() 이 이걸로 덮어쓰거나 새로 만들지 않는다.
users_table = Table(
    "users",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    extend_existing=True,
)


class AdviceLog(Base):
    __tablename__ = "advice_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    query_type = Column(String(20), nullable=False)  # 'RECOMMEND' | 'SEARCH'
    user_query = Column(Text, nullable=False)
    gemini_response = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class CustomSynthesisLog(Base):
    __tablename__ = "custom_synthesis_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    selected_asset_id = Column(String(100), nullable=True)
    result_image_url = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class Vehicle(Base):
    """마이페이지 '내 차량' 카드 1개에 대응하는 유저당 차량 1대.

    user_id 는 users.id 를 실제 FK로 참조한다 (ON DELETE CASCADE).
    users 테이블은 SQLAlchemy 모델이 아니라 db/schema.sql 로 수동 생성되므로,
    이 FK가 걸리려면 create_all 실행 시점에 users 테이블이 이미 DB에 있어야 한다.
    """

    __tablename__ = "vehicles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    name = Column(String(100), nullable=False)
    image_url = Column(Text, nullable=True)
    pcd = Column(String(50), nullable=True)
    hole_count = Column(String(20), nullable=True)
    hub_bore = Column(String(50), nullable=True)
    bolt_spec = Column(String(50), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())