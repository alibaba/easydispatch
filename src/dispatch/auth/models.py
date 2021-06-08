import string
import secrets
from typing import List
from enum import Enum
from datetime import datetime, timedelta, date

import bcrypt
from jose import jwt
from typing import Optional
from pydantic import validator, Field
from sqlalchemy import Column, String, Binary, Integer, Boolean

from dispatch.database import Base
from dispatch.models import TimeStampMixin, DispatchBase

from dispatch.config import (
    DISPATCH_JWT_SECRET,
    DISPATCH_JWT_ALG,
    DISPATCH_JWT_EXP,
)


def generate_password():
    """Generates a resonable password if none is provided."""
    alphanumeric = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphanumeric) for i in range(10))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and sum(c.isdigit() for c in password) >= 3
        ):
            break
    return password


def hash_password(password: str):
    """Generates a hashed version of the provided password."""
    pw = bytes(password, "utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw, salt)


class UserRoles(str, Enum):
    user = "User"
    poweruser = "Poweruser"
    admin = "Admin"


class DispatchUser(Base, TimeStampMixin):
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(Binary, nullable=False)
    role = Column(String, nullable=False, default=UserRoles.user)
    is_org_owner = Column(Boolean, nullable=True, default=False)
    org_id = Column(Integer, nullable=False, default=0)
    org_code = Column(String, nullable=False, default="0")
    is_team_owner = Column(Boolean, nullable=True, default=False)
    # team_code = Column(String, nullable=True, default="t1")
    default_team_id = Column(Integer, default=1)
    # https://avatars1.githubusercontent.com/u/5224736?s=400&u=c9dd310fdfea18388a409197a3f5f4f6b64af46e&v=4
    thumbnail_photo_url = Column(String)
    full_name = Column(String)

    is_team_worker = Column(Boolean, nullable=True, default=False)
    """
    """

    def check_password(self, password):
        return bcrypt.checkpw(password.encode("utf-8"), self.password)

    @property
    def token(self):
        # now = datetime.utcnow()
        today = date.today()
        now = datetime(
            year=today.year,
            month=today.month,
            day=today.day,
        )
        exp = (now + timedelta(seconds=int(DISPATCH_JWT_EXP))).timestamp()
        data = {
            "exp": exp,
            "email": self.email,
            "org_code": self.org_code,
            "role": self.role,
            "default_team_id": self.default_team_id,
        }
        return jwt.encode(data, DISPATCH_JWT_SECRET, algorithm=DISPATCH_JWT_ALG)

    def principals(self):
        return [f"user:{self.email}", f"role:{self.role}"]


class UserBase(DispatchBase):
    email: str = Field(
        default=None, title="username or email", description="The username to login. Though name is email, it may not be email format.",)

    @validator("email")
    def email_required(cls, v):
        if not v:
            raise ValueError("Must not be empty string and must be a email")
        return v


class UserLogin(UserBase):
    password: str

    @validator("password")
    def password_required(cls, v):
        if not v:
            raise ValueError("Must not be empty string")
        return v


class UserRegister(UserLogin):
    password: Optional[str]
    role: UserRoles = Field(
        default=UserRoles.user, title="user role", description="in current version, all users have user roles",)

    """
    org_code: Optional[str]
    is_org_owner: Optional[bool]
    """

    @validator("password", pre=True, always=True)
    def password_required(cls, v):
        # we generate a password for those that don't have one
        password = v or generate_password()
        return hash_password(password)


class UserLoginResponse(DispatchBase):
    token: Optional[str]


class UserRead(UserBase):
    id: int
    role: str
    org_code: str
    default_team_id: int
    is_org_owner: bool
    is_team_owner: bool
    thumbnail_photo_url: Optional[str]
    full_name: Optional[str]


class UserUpdate(DispatchBase):
    id: int
    role: UserRoles


class UserRegisterResponse(DispatchBase):
    email: str
    org_code: str
    default_team_id: int
    is_org_owner: bool


class UserPagination(DispatchBase):
    total: int
    items: List[UserRead] = []
