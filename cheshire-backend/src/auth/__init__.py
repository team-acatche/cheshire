from enum import Enum, auto
from pathlib import Path

from auth.models import User, generate_salt
from auth.user_repository import UserRepository, SqliteUserRepository
from auth.hashers import Argon2PasswordHasher


class UserRepositoryType(Enum):
    SQLITE = auto()


async def get_or_create_user_repository(path: Path, *, repository_type: UserRepositoryType = UserRepositoryType.SQLITE) -> UserRepository:
    if repository_type == UserRepositoryType.SQLITE:
        return SqliteUserRepository(path, hasher=Argon2PasswordHasher())
    else:
        raise ValueError(f"Unsupported repository type: {repository_type}")
