from sqlalchemy import Column, Integer, String, BigInteger, DateTime
from sqlalchemy.sql import func
from .base import Base

class Admin(Base):
    __tablename__ = 'admins'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)  # آیدی عددی تلگرام
    username = Column(String(100), nullable=True)              # یوزرنیم (نمایشی)
    promoted_by = Column(String(100), nullable=True)           # نام کسی که او را ادمین کرده
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Admin(user_id={self.user_id}, username='{self.username}')>"