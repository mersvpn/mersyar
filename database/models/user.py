# --- START OF FILE database/models/user.py ---
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DECIMAL,
    Integer,
    String,
    TIMESTAMP,
    Text,
)

from sqlalchemy import (
    BigInteger,
    Boolean,
    DECIMAL,
    Integer,
    String,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

if TYPE_CHECKING:
    from .marzban_link import MarzbanTelegramLink
    from .pending_invoice import PendingInvoice
    from .broadcast import Broadcast


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    join_date: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now()
    )
    wallet_balance: Mapped[Decimal] = mapped_column(
        DECIMAL(15, 2), nullable=False, default=Decimal("0.00")
    )
    test_accounts_received: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_activity: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)


    # Relationships
    marzban_links: Mapped[List["MarzbanTelegramLink"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    pending_invoices: Mapped[List["PendingInvoice"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    broadcasts: Mapped[List["Broadcast"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.user_id}, username='{self.username}')>"

# --- END OF FILE database/models/user.py ---