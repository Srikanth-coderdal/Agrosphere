from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from database import Base


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, index=True)
    email: str = Column(String, unique=True, index=True, nullable=False)
    hashed_password: str = Column(String, nullable=False)
    full_name: str = Column(String, nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: int = Column(Integer, primary_key=True, index=True)
    jti: str = Column(String, unique=True, index=True, nullable=False)
    token_hash: str = Column(String, unique=True, index=True, nullable=False)
    revoked_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ConsentedUpload(Base):
    __tablename__ = "consented_uploads"

    id: int = Column(Integer, primary_key=True, index=True)
    upload_id: str = Column(String, unique=True, index=True, nullable=False)
    user_id: int = Column(Integer, index=True, nullable=False)
    filename: str = Column(String, unique=True, nullable=False)
    crop_type: str = Column(String, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class QuotaLedgerRecord(Base):
    __tablename__ = "quota_ledger"

    id: int = Column(Integer, primary_key=True, index=True)
    bucket_type: str = Column(String, index=True, nullable=False)  # 'day' or 'minute'
    bucket_key: str = Column(String, unique=True, index=True, nullable=False)
    call_count: int = Column(Integer, default=0, nullable=False)
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UserScanQuota(Base):
    __tablename__ = "user_scan_quotas"

    id: int = Column(Integer, primary_key=True, index=True)
    user_id: int = Column(Integer, index=True, nullable=False)
    day_key: str = Column(String, index=True, nullable=False)
    scan_count: int = Column(Integer, default=0, nullable=False)
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

