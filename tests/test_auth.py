import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User, UserRole
from src.services.auth_service import ensure_admin_exists, hash_password


async def create_test_user(
    session: AsyncSession,
    email: str,
    password: str,
    role: UserRole = UserRole.teacher,
    first_name: str = "Test",
    last_name: str = "User",
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login_user(
    client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    response = await client.post(
        "/auth/login",
        data={"username": email, "password": password},
    )
    return dict(response.json())


async def get_auth_header(
    client: AsyncClient, email: str, password: str
) -> dict[str, str]:
    data = await login_user(client, email, password)
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.mark.asyncio
async def test_login_valid(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(db_session, "valid@stuba.sk", "secret123")
    response = await test_client.post(
        "/auth/login",
        data={"username": "valid@stuba.sk", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(db_session, "invalid@stuba.sk", "correct")
    response = await test_client.post(
        "/auth/login",
        data={"username": "invalid@stuba.sk", "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_me_valid_token(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "me@stuba.sk", "pass123",
        first_name="Jan", last_name="Novak",
    )
    headers = await get_auth_header(test_client, "me@stuba.sk", "pass123")
    response = await test_client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "me@stuba.sk"
    assert body["first_name"] == "Jan"
    assert body["last_name"] == "Novak"
    assert body["role"] == "teacher"


@pytest.mark.asyncio
async def test_me_invalid_token(test_client: AsyncClient) -> None:
    response = await test_client.get(
        "/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_as_admin(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "admin@stuba.sk", "admin", role=UserRole.admin,
    )
    headers = await get_auth_header(test_client, "admin@stuba.sk", "admin")
    response = await test_client.post(
        "/auth/register",
        json={
            "email": "new@stuba.sk",
            "password": "newpass",
            "first_name": "New",
            "last_name": "Teacher",
            "role": "teacher",
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@stuba.sk"
    assert body["first_name"] == "New"
    assert body["role"] == "teacher"


@pytest.mark.asyncio
async def test_register_as_teacher_forbidden(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(
        db_session, "teacher@stuba.sk", "teacherpass",
    )
    headers = await get_auth_header(
        test_client, "teacher@stuba.sk", "teacherpass"
    )
    response = await test_client.post(
        "/auth/register",
        json={
            "email": "another@stuba.sk",
            "password": "pass",
            "first_name": "A",
            "last_name": "B",
        },
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_auto_admin_creation(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await ensure_admin_exists(db_session)
    response = await test_client.post(
        "/auth/login",
        data={"username": "admin@stuba.sk", "password": "admin"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    me_response = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_public_endpoints_no_auth(test_client: AsyncClient) -> None:
    health = await test_client.get("/health")
    assert health.status_code == 200

    scans = await test_client.get("/scans?limit=10&offset=0")
    assert scans.status_code == 200


@pytest.mark.asyncio
async def test_cors_headers(test_client: AsyncClient) -> None:
    response = await test_client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_openapi_schema(test_client: AsyncClient) -> None:
    docs = await test_client.get("/docs")
    assert docs.status_code == 200

    openapi = await test_client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    assert "/auth/login" in schema["paths"]
    assert "/auth/me" in schema["paths"]
    assert "/auth/register" in schema["paths"]


@pytest.mark.asyncio
async def test_oauth2_bearer(
    test_client: AsyncClient, db_session: AsyncSession
) -> None:
    await create_test_user(db_session, "oauth@stuba.sk", "oauthpass")
    login_resp = await test_client.post(
        "/auth/login",
        data={"username": "oauth@stuba.sk", "password": "oauthpass"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = await test_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "oauth@stuba.sk"
