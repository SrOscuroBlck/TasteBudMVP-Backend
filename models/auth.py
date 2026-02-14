from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON
import secrets


class UserSession(SQLModel, table=True):
    __tablename__ = "user_session"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    token: str = Field(unique=True, index=True)
    refresh_token: str = Field(unique=True, index=True)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    last_used_at: datetime = Field(default_factory=datetime.utcnow)
    
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    is_active: bool = True


class OTPCode(SQLModel, table=True):
    __tablename__ = "otp_code"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    code: str = Field(index=True)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    used_at: Optional[datetime] = None
    
    is_used: bool = False
    attempts: int = 0
    max_attempts: int = 3
    
    @staticmethod
    def generate_code() -> str:
        return ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    
    def is_valid(self) -> bool:
        if self.is_used:
            return False
        if self.attempts >= self.max_attempts:
            return False
        if datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def increment_attempts(self):
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            self.is_used = True
