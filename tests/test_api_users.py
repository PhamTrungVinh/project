def test_get_me_authenticated(client, test_user, auth_headers):
    response = client.get("/users/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email
    assert data["full_name"] == test_user.full_name


def test_get_me_unauthenticated(client):
    response = client.get("/users/me")
    assert response.status_code == 401


def test_get_me_invalid_token(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer invalid_token"})
    assert response.status_code == 401
