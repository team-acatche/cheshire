from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Protocol, Optional
from uuid import uuid4

from fastapi import HTTPException, status

from auth.models import User, UserEntity, generate_salt
from auth.hashers import PasswordHasher

class UserRepository(Protocol):
    def create_table_if_not_exists(self):
        """
        Create the user table if it does not exist.
        """
        ...

    def login(self, email: str, password: str) -> UserEntity:
        """
        Login a user with their email and password.
        """
        ...

    def register(
        self,
        email: str,
        password: str,
        *,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> UserEntity:
        """
        Register a new user.
        """
        ...

    def get_by_user_id(self, user_id: str) -> Optional[UserEntity]:
        """
        Get a user by their user ID.
        """
        ...

    def update_avatar(self, user_id: str, avatar_uri: str) -> UserEntity:
        """
        Update the avatar URI for a given user.
        """
        ...

class InMemoryUserRepository(UserRepository):
    def __init__(self, *, hasher: PasswordHasher):
        self.users: dict[str, UserEntity] = {}
        self.hasher = hasher

    def create_table_if_not_exists(self):
        pass

    def login(self, email: str, password: str) -> UserEntity:
        if email not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {email} not found",
            )
        user_entity = self.users[email]

        if not self.hasher.verify(
            f"{user_entity.prefix_salt}{password}{user_entity.suffix_salt}",
            user_entity.password_hash,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid username or password for {email}",
            )
        if user_entity.disabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{email} is disabled",
            )
        return user_entity

    def register(
        self,
        email: str,
        password: str,
        *,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> UserEntity:
        if email in self.users:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{email} already exists",
            )

        prefix_salt = generate_salt()
        suffix_salt = generate_salt()
        new_user = UserEntity(
            user=User(
                email=email,
                username=username,
                full_name=full_name,
            ),
            password_hash=self.hasher.hash(f"{prefix_salt}{password}{suffix_salt}"),
            prefix_salt=prefix_salt,
            suffix_salt=suffix_salt,
        )
        self.users[email] = new_user

        return new_user

    def get_by_user_id(self, user_id: str) -> Optional[UserEntity]:
        for user_entity in self.users.values():
            if user_entity.user.user_id == user_id:
                return user_entity
        return None
    
    def update_avatar(self, user_id: str, avatar_uri: str) -> UserEntity:
        if user_id not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with user ID `{user_id}` not found",
            )
        self.users[user_id].user.avatar_uri = avatar_uri
        return self.users[user_id]


class SqliteUserRepository(UserRepository):
    def __init__(self, db_path: Path, *, hasher: PasswordHasher):
        self.db_path = db_path
        self.hasher = hasher

    def create_table_if_not_exists(self):
        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    sessions_folder TEXT NOT NULL,
                    username TEXT UNIQUE,
                    full_name TEXT DEFAULT 'user',
                    avatar_uri TEXT DEFAULT 'avatars/default.png',
                    password_hash TEXT NOT NULL,
                    prefix_salt TEXT NOT NULL,
                    suffix_salt TEXT NOT NULL,
                    disabled BOOLEAN DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS username_idx ON user(username);")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS email_idx ON user(email);")
            conn.commit()

    def login(self, email: str, password: str) -> UserEntity:
        self.create_table_if_not_exists()
        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id,
                       email,
                       sessions_folder,
                       username,
                       full_name,
                       avatar_uri,
                       password_hash,
                       prefix_salt,
                       suffix_salt,
                       disabled,
                       created_at
                FROM user
                WHERE email = ?
                LIMIT 1;
            """, (email,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with email `{email}` not found",
                )

            user = UserEntity.from_row(row)

            if not self.hasher.verify(
                f"{user.prefix_salt}{password}{user.suffix_salt}",
                user.password_hash,
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid username or password for {email}",
                )
            if user.disabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"User for email `{email}` is disabled",
                )

            return user

    def register(
        self,
        email: str,
        password: str,
        *,
        username: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> UserEntity:
        self.create_table_if_not_exists()

        prefix_salt = generate_salt()
        suffix_salt = generate_salt()
        new_user = UserEntity(
            user=User(
                email=email,
                username=username,
                full_name=full_name,
            ),
            password_hash=self.hasher.hash(f"{prefix_salt}{password}{suffix_salt}"),
            prefix_salt=prefix_salt,
            suffix_salt=suffix_salt,
        )

        fields_and_values = {
            # User
            "user_id": new_user.user.user_id,
            "email": new_user.user.email,
            "sessions_folder": new_user.user.sessions_folder,
            "avatar_uri": new_user.user.avatar_uri,
            # UserEntity
            "password_hash": new_user.password_hash,
            "prefix_salt": new_user.prefix_salt,
            "suffix_salt": new_user.suffix_salt,
            "disabled": new_user.disabled,
            "created_at": new_user.created_at,
        }

        if full_name is not None:
            fields_and_values["full_name"] = full_name

        if username is not None:
            fields_and_values["username"] = username

        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"INSERT INTO user ({', '.join(fields_and_values.keys())}) VALUES ({', '.join(['?'] * len(fields_and_values))})",
                    list(fields_and_values.values()),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User with email `{email}` already exists",
                )
            conn.commit()

            return new_user

    def get_by_user_id(self, user_id: str) -> Optional[UserEntity]:
        self.create_table_if_not_exists()
        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id,
                       email,
                       sessions_folder,
                       username,
                       full_name,
                       avatar_uri,
                       password_hash,
                       prefix_salt,
                       suffix_salt,
                       disabled,
                       created_at
                FROM user
                WHERE user_id = ?
                LIMIT 1;
            """, (user_id,))
            row = cursor.fetchone()

            if row is None:
                return None

            return UserEntity.from_row(row)
    
    def update_avatar(self, user_id: str, avatar_uri: str) -> UserEntity:
        self.create_table_if_not_exists()
        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""UPDATE user SET avatar_uri = ? WHERE user_id = ? RETURNING *""", (avatar_uri, user_id))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with user ID `{user_id}` not found",
                )
            conn.commit()

            return UserEntity.from_row(row)