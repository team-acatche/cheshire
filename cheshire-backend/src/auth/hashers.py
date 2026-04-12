from typing import Protocol

from pwdlib import PasswordHash

class PasswordHasher(Protocol):
    def hash(self, password: str) -> str:
        pass

    def verify(self, password: str, hashed_password: str) -> bool:
        pass

class Argon2PasswordHasher(PasswordHasher):
    def __init__(self):
        self.hasher = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self.hasher.hash(password)

    def verify(self, password: str, hashed_password: str) -> bool:
        return self.hasher.verify(password, hashed_password)
