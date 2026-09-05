def test_register_success(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "Password123!",
            "full_name": "New User",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data


def test_register_duplicate_email(client, test_user):
    response = client.post(
        "/auth/register",
        json={
            "email": test_user.email,
            "password": "AnyPassword123!",
            "full_name": "Duplicate User",
        },
    )
    assert response.status_code == 409


def test_login_success(client, test_user):
    response = client.post(
        "/auth/login",
        data={
            "username": test_user.email,
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/auth/login",
        data={
            "username": test_user.email,
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = client.post(
        "/auth/login",
        data={
            "username": "doesnotexist@example.com",
            "password": "SomePassword123!",
        },
    )
    assert response.status_code == 401
