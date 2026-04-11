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
        pass

    def login(self, email: str, password: str) -> UserEntity:
        pass

    def register(self, email: str, password: str, *, username: Optional[str] = None, full_name: Optional[str] = None) -> UserEntity:
        pass

class InMemoryUserRepository(UserRepository):
    def __init__(self, *, hasher: PasswordHasher):
        self.users: dict[str, UserEntity] = {}
        self.hasher = hasher

    def create_table_if_not_exists(self):
        pass

    def login(self, email: str, password: str) -> UserEntity:
        if email not in self.users:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User {email} not found")
        user_entity = self.users[email]

        if not self.hasher.verify(f"{user_entity.prefix_salt}{password}{user_entity.suffix_salt}", user_entity.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid username or password for {email}")
        if user_entity.disabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{email} is disabled")
        return user_entity

    def register(self, email: str, password: str, *, username: Optional[str] = None, full_name: Optional[str] = None) -> UserEntity:
        if email in self.users:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{email} already exists")

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
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with email `{email}` not found")

            user = UserEntity(
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

            if not self.hasher.verify(f"{user.prefix_salt}{password}{user.suffix_salt}", user.password_hash):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid username or password for {email}")
            if user.disabled:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"User for email `{email}` is disabled")

            return user

    def register(self,
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
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User with email `{email}` already exists")
            conn.commit()

            return new_user
