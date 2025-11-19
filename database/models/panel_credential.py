# FILE: database/models/panel_credential.py (REVISED AND CORRECTED)

from sqlalchemy import Integer, String, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import false
import enum

from . import Base


# Define an Enum for panel types for data consistency.
# MODIFIED: Enum members are now uppercase to match the data ('MARZBAN')
# currently in the database. This directly resolves the LookupError.
# This is also a more common convention for Enum members.
class PanelType(str, enum.Enum):
    MARZBAN = "MARZBAN"
    XUI = "X-UI"
    MARZNESHIN = "MARZNESHIN"

class PanelCredential(Base):
    __tablename__ = "panel_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    
    # MODIFIED: Simplified the SQLAlchemyEnum definition.
    # The `values_callable` is no longer needed. SQLAlchemy's default behavior
    # of storing the Enum member names ('MARZBAN') as strings is exactly what we need.
    panel_type: Mapped[PanelType] = mapped_column(
        SQLAlchemyEnum(PanelType),
        nullable=False
    )
    
    api_url: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    is_test_panel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    def __repr__(self) -> str:
        # Accessing .value is still correct, it will return the string "MARZBAN", etc.
        return f"<PanelCredential(id={self.id}, name='{self.name}', type='{self.panel_type.value}')>"