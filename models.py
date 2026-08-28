from sqlalchemy import Column, BigInteger, String, Text, TIMESTAMP, func
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