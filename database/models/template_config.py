# --- START: Replace entire file database/models/template_config.py ---
from sqlalchemy import Integer, String, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from . import Base

class TemplateConfig(Base):
    __tablename__ = "template_config"

    # ✨ MODIFIED: The primary key is now a standard auto-incrementing integer.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # ✨ NEW: Foreign key to link this template to a specific panel.
    # This makes the relationship one-to-one (each panel has one template config).
    panel_id: Mapped[int] = mapped_column(Integer, ForeignKey("panel_credentials.id"), unique=True, nullable=False)
    
    template_username: Mapped[str] = mapped_column(String(255), nullable=False)
    proxies: Mapped[dict] = mapped_column(JSON, nullable=True)
    inbounds: Mapped[dict] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<TemplateConfig(panel_id={self.panel_id}, username='{self.template_username}')>"

# --- END: Replacement ---