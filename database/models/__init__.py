# FILE: database/models/__init__.py (CORRECTED AND COMPLETE)

from sqlalchemy.orm import DeclarativeBase

# 1. Define the Base class first
class Base(DeclarativeBase):
    """The base class for all SQLAlchemy ORM models in the project."""
    pass

# 2. Now, import all your model classes so that SQLAlchemy and Alembic can see them.
#    This is the crucial step that was missing.
from .user import User
from .panel_credential import PanelCredential
from .marzban_link import MarzbanTelegramLink
from .user_note import UserNote
from .bot_managed_user import BotManagedUser
from .template_config import TemplateConfig
from .non_renewal_user import NonRenewalUser
from .pending_invoice import PendingInvoice
from .broadcast import Broadcast
from .financial_setting import FinancialSetting
from .guide import Guide
from .unlimited_plan import UnlimitedPlan
from .volumetric_tier import VolumetricTier
from .admin_daily_note import AdminDailyNote
from .bot_setting import BotSetting

# 3. (Optional but good practice) Define __all__ to control what `from .models import *` imports.
__all__ = [
    "Base",
    "User",
    "PanelCredential",
    "MarzbanTelegramLink",
    "UserNote",
    "BotManagedUser",
    "TemplateConfig",
    "NonRenewalUser",
    "PendingInvoice",
    "Broadcast",
    "FinancialSetting",
    "Guide",
    "UnlimitedPlan",
    "VolumetricTier",
    "AdminDailyNote",
]