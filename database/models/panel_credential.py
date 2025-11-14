# FILE: database/models/panel_credential.py (MODIFIED)

from sqlalchemy import Integer, String, Enum as SQLAlchemyEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import false
import enum

from . import Base


# Define an Enum for panel types for data consistency
# MODIFIED: Member names are now lowercase to match values and prevent LookupError.
# This makes the code consistent with the data stored in the database.
class PanelType(str, enum.Enum):
    marzban = "marzban"
    x_ui = "x-ui"  # Identifier uses underscore, but value is "x-ui"
    marzneshin = "marzneshin"

class PanelCredential(Base):
    __tablename__ = "panel_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    
    # MODIFIED: Added `values_callable` to ensure SQLAlchemy uses the string values directly,
    # which is a more robust way to handle string-based Enums.
    panel_type: Mapped[PanelType] = mapped_column(
        SQLAlchemyEnum(PanelType, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False
    )
    
    api_url: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    is_test_panel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    def __repr__(self) -> str:
        # No changes needed here, as .value correctly accesses the string representation.
        return f"<PanelCredential(id={self.id}, name='{self.name}', type='{self.panel_type.value}')>"