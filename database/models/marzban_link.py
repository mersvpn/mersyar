# --- START OF FILE database/models/marzban_link.py ---
from __future__ import annotations # ✨ FIX: This MUST be the very first line of code

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import Base

if TYPE_CHECKING:
    from .user import User
    from .user_note import UserNote
    from .panel_credential import PanelCredential

class MarzbanTelegramLink(Base):
    __tablename__ = "marzban_telegram_links"

    marzban_username: Mapped[str] = mapped_column(String(255), primary_key=True)
    panel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("panel_credentials.id"), nullable=False
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=False, index=True
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationship to the UserNote model (one-to-one)
    user_note: Mapped[Optional["UserNote"]] = relationship(
        "UserNote",
        primaryjoin="foreign(MarzbanTelegramLink.marzban_username) == UserNote.username",
        back_populates="link",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True  # This flag resolves the cascade error
    )

    # Relationship to the User model
    user: Mapped["User"] = relationship(back_populates="marzban_links")

    def __repr__(self) -> str:
        return f"<MarzbanTelegramLink(marzban='{self.marzban_username}', telegram_id={self.telegram_user_id})>"
    
    # Relationship to the PanelCredential model
    panel: Mapped["PanelCredential"] = relationship(
        "PanelCredential",
        primaryjoin="foreign(MarzbanTelegramLink.panel_id) == PanelCredential.id",
        backref="marzban_links"
    )


# --- END OF FILE database/models/marzban_link.py ---