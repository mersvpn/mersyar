#database/models/base.py

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """The base class for all SQLAlchemy ORM models in the project."""
    pass