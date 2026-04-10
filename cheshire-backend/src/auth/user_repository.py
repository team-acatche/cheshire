from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Protocol, Optional
from uuid import uuid4

from fastapi import HTTPException

from auth.models import User, UserEntity, generate_salt
from auth.hashers import PasswordHasher

class UserRepository(Protocol):
    def create_table_if_not_exists(self):
        pass

    def login(self, username: str, password: str) -> UserEntity:
        pass

    def register(self, username: str, password: str, full_name: Optional[str] = None) -> UserEntity:
        pass

class InMemoryUserRepository(UserRepository):
    def __init__(self, *, hasher: PasswordHasher):
        self.users: dict[str, UserEntity] = {}
        self.hasher = hasher

    def create_table_if_not_exists(self):
        pass

    def login(self, username: str, password: str) -> UserEntity:
        if username not in self.users:
            raise HTTPException(status_code=404, detail=f"User {username} not found")
        user_entity = self.users[username]

        if not self.hasher.verify(f"{user_entity.prefix_salt}{password}{user_entity.suffix_salt}", user_entity.password_hash):
            raise HTTPException(status_code=401, detail=f"Invalid password for user {username}")
        if user_entity.disabled:
            raise HTTPException(status_code=403, detail=f"User {username} is disabled")
        return user_entity

    def register(self, username: str, password: str, full_name: Optional[str] = None) -> UserEntity:
        if username in self.users:
            raise HTTPException(status_code=409, detail=f"User {username} already exists")

        prefix_salt = generate_salt()
        suffix_salt = generate_salt()
        new_user = UserEntity(
            user=User(
                username=username,
                sessions_folder=username,
                full_name=full_name,
            ),
            password_hash=self.hasher.hash(f"{prefix_salt}{password}{suffix_salt}"),
            prefix_salt=prefix_salt,
            suffix_salt=suffix_salt,
        )
        self.users[username] = new_user

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
                    username TEXT NOT NULL UNIQUE,
                    sessions_folder TEXT NOT NULL,
                    full_name TEXT DEFAULT 'user',
                    avatar_uri TEXT DEFAULT 'avatars/default.png',
                    password_hash TEXT NOT NULL,
                    prefix_salt TEXT NOT NULL,
                    suffix_salt TEXT NOT NULL,
                    disabled BOOLEAN DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS username_idx ON user(username);")
            conn.commit()

    def login(self, username: str, password: str) -> UserEntity:
        self.create_table_if_not_exists()
        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id,
                       username,
                       sessions_folder,
                       full_name,
                       avatar_uri,
                       password_hash,
                       prefix_salt,
                       suffix_salt,
                       disabled,
                       created_at
                FROM user
                WHERE username = ?
                LIMIT 1;
            """, (username,))
            row = cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"User {username} not found")

            user = UserEntity(
                user=User(
                    user_id=row[0],
                    username=row[1],
                    sessions_folder=row[2],
                    full_name=row[3],
                    avatar_uri=row[4],
                ),
                password_hash=row[5],
                prefix_salt=row[6],
                suffix_salt=row[7],
                disabled=bool(row[8]),
                created_at=row[9],
            )

            if not self.hasher.verify(f"{user.prefix_salt}{password}{user.suffix_salt}", user.password_hash):
                raise HTTPException(status_code=401, detail=f"Invalid password for user {username}")
            if user.disabled:
                raise HTTPException(status_code=403, detail=f"User {username} is disabled")

            return user

    def register(self,
        username: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> UserEntity:
        self.create_table_if_not_exists()

        prefix_salt = generate_salt()
        suffix_salt = generate_salt()
        new_user = UserEntity(
            user=User(
                username=username,
                sessions_folder=username,
                full_name=full_name,
            ),
            password_hash=self.hasher.hash(f"{prefix_salt}{password}{suffix_salt}"),
            prefix_salt=prefix_salt,
            suffix_salt=suffix_salt,
        )

        fields_and_values = {
            # User
            "user_id": new_user.user.user_id,
            "username": new_user.user.username,
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

        with sqlite3.connect(self.db_path, uri=True) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"INSERT INTO user ({', '.join(fields_and_values.keys())}) VALUES ({', '.join(['?'] * len(fields_and_values))})",
                    list(fields_and_values.values()),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=409, detail=f"User {username} already exists")

            conn.commit()
            return new_user
