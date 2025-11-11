# FILE: database/models/panel_credential.py (MODIFIED)

from sqlalchemy import Integer, String, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import false
import enum

from . import Base


# Define an Enum for panel types for data consistency
class PanelType(str, enum.Enum):
    MARZBAN = "marzban"
    XUI = "x-ui"
    MARZNESHIN = "marzneshin"

class PanelCredential(Base):
    __tablename__ = "panel_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    panel_type: Mapped[PanelType] = mapped_column(SQLAlchemyEnum(PanelType), nullable=False)
    api_url: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # ✨ NEW COLUMN ADDED HERE
    is_test_panel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    def __repr__(self) -> str:
        return f"<PanelCredential(id={self.id}, name='{self.name}', type='{self.panel_type.value}')>"
    
