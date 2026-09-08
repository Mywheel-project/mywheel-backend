from sqlalchemy import Column, BigInteger, Integer, String, Text, TIMESTAMP, func, UniqueConstraint
from database import Base


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


class UserWheelFavorite(Base):
    __tablename__ = "user_wheel_favorites"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    wheel_id = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "wheel_id", name="uq_user_wheel_favorite"),
    )