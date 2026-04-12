from enum import Enum

from pydantic import BaseModel


class UserRole(str, Enum):
    CFL = "CFL" # superadmin has higher privileges than admin; only they can promote to admin
    ADMIN = "admin"
    PUBLIC = "public"

class FirebaseUser(BaseModel):
    user_id: str
    role: UserRole

class FirebaseUserE(FirebaseUser):
    email: str
    name:str | None = None