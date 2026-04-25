from datetime import datetime
import random
import string
from typing import Annotated, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

def generate_salt() -> str:
    SALT_LENGTH: int = 16
    return ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(SALT_LENGTH))

class User(BaseModel):
    email: str
    user_id: str = Field(default_factory=lambda: str(uuid4()))
    sessions_folder: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_uri: str = "avatars/default.png"

    def model_post_init(self, __context):
        if not self.sessions_folder:
            self.sessions_folder = self.user_id

class UserEntity(BaseModel):
    user: User
    password_hash: str
    prefix_salt: str = Field(default_factory=generate_salt)
    suffix_salt: str = Field(default_factory=generate_salt)
    disabled: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @staticmethod
    def from_row(row: tuple) -> "UserEntity":
        return UserEntity(
            user=User(
                user_id=row[0],
                email=row[1],
                sessions_folder=row[2],
                username=row[3],
                full_name=row[4],
                avatar_uri=row[5],
            ),
            password_hash=row[6],
            prefix_salt=row[7],
            suffix_salt=row[8],
            disabled=bool(row[9]),
            created_at=row[10],
        )
