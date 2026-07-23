from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserLogin, UserRegister


class AuthService:
    """Regras de negócio de autenticação."""

    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def register(self, data: UserRegister) -> User:
        if self.users.get_by_email(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="E-mail já cadastrado.",
            )
        return self.users.create(
            name=data.name,
            email=data.email,
            password_hash=hash_password(data.password),
        )

    def login(self, data: UserLogin) -> tuple[str, User]:
        user = self.users.get_by_email(data.email)
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="E-mail ou senha incorretos.",
            )
        return create_access_token(str(user.id)), user

    def get_user_by_token(self, token: str) -> User:
        subject = decode_access_token(token)
        user = self.users.get_by_id(int(subject)) if subject else None
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão inválida ou expirada.",
            )
        return user
