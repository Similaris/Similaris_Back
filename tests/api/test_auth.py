from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pytest

from app.core.database import Base, get_db
from app.main import app
from app.models.auth import User


@pytest.fixture()
def auth_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_register_and_case_insensitive_login(auth_client):
    register_res = auth_client.post(
        "/api/auth/register",
        json={
            "name": "  Rafael Praca  ",
            "email": "  Rafael.Praca@FATEC.sp.gov.br  ",
            "password": "secretpassword123",
        },
    )
    assert register_res.status_code == 201
    registered_data = register_res.json()
    assert registered_data["name"] == "Rafael Praca"
    assert registered_data["email"] == "rafael.praca@fatec.sp.gov.br"

    # Tentativa de registrar o mesmo e-mail em minúsculas deve retornar 409
    dup_res = auth_client.post(
        "/api/auth/register",
        json={
            "name": "Rafael",
            "email": "rafael.praca@fatec.sp.gov.br",
            "password": "anotherpassword",
        },
    )
    assert dup_res.status_code == 409

    # Login com e-mail em minúsculas deve funcionar
    login_res = auth_client.post(
        "/api/auth/login",
        json={
            "email": "rafael.praca@fatec.sp.gov.br",
            "password": "secretpassword123",
        },
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data

    # Acesso ao /auth/me usando o access token
    me_res = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "rafael.praca@fatec.sp.gov.br"

    # Refresh do token
    refresh_res = auth_client.post(
        "/api/auth/refresh",
        json={"refresh_token": token_data["refresh_token"]},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens


def test_register_blank_name_fails(auth_client):
    res = auth_client.post(
        "/api/auth/register",
        json={
            "name": "   ",
            "email": "teste@exemplo.com",
            "password": "password123",
        },
    )
    assert res.status_code == 422


def test_login_invalid_password(auth_client):
    auth_client.post(
        "/api/auth/register",
        json={
            "name": "Usuario Teste",
            "email": "usuario@exemplo.com",
            "password": "corretapassword",
        },
    )
    res = auth_client.post(
        "/api/auth/login",
        json={
            "email": "usuario@exemplo.com",
            "password": "erradapassword",
        },
    )
    assert res.status_code == 401
