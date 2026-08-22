from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.auth import User
from app.repositories.auth import UserRepository
from app.schemas.auth import UserLogin, UserRegister


class AuthService:

    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def register(self, data: UserRegister) -> User:
        if self.users.get_by_email(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="E-mail já cadastrado."
            )
        return self.users.create(
            name=data.name, email=data.email, password_hash=hash_password(data.password)
        )

    def login(self, data: UserLogin) -> tuple[str, str, User]:
        user = self.users.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail ou senha incorretos.",
            )
        access_token, refresh_token = self._create_token_pair(user)
        return access_token, refresh_token, user

    def refresh(self, refresh_token: str) -> tuple[str, str, User]:
        subject = decode_refresh_token(refresh_token)
        user = self.users.get_by_id(int(subject)) if subject and subject.isdigit() else None
        if not user:
            raise self._invalid_session()
        access_token, new_refresh_token = self._create_token_pair(user)
        return access_token, new_refresh_token, user

    @staticmethod
    def _create_token_pair(user: User) -> tuple[str, str]:
        return create_access_token(str(user.id)), create_refresh_token(str(user.id))

    @staticmethod
    def _invalid_session() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada.",
        )

    def get_user_by_token(self, token: str) -> User:
        subject = decode_access_token(token)
        user = self.users.get_by_id(int(subject)) if subject and subject.isdigit() else None
        if not user:
            raise self._invalid_session()
        return user
