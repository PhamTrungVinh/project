def test_create_and_get_ticket(client, auth_headers):
    payload = {
        "content": "VPN issue",
        "description": "Cannot connect to VPN from home",
        "customer_name": "Charlie",
        "customer_phone": "0123456789",
        "email": "charlie@example.com",
    }
    create_resp = client.post("/tickets/", json=payload, headers=auth_headers)
    assert create_resp.status_code == 200
    ticket_data = create_resp.json()
    assert ticket_data["content"] == "VPN issue"
    assert ticket_data["status"] == "Pending"
    ticket_code = ticket_data["ticket_code"]

    # Get by code
    get_resp = client.get(f"/tickets/{ticket_code}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["ticket_code"] == ticket_code


def test_list_tickets(client, auth_headers):
    # Create two tickets
    for i in range(2):
        client.post(
            "/tickets/",
            json={"content": f"Issue {i}", "description": f"Desc {i}"},
            headers=auth_headers,
        )

    response = client.get("/tickets/", headers=auth_headers)
    assert response.status_code == 200
    tickets = response.json()
    assert len(tickets) >= 2


def test_update_ticket(client, auth_headers):
    create_resp = client.post(
        "/tickets/",
        json={"content": "Original Content", "description": "Original Desc"},
        headers=auth_headers,
    )
    ticket_code = create_resp.json()["ticket_code"]

    patch_resp = client.patch(
        f"/tickets/{ticket_code}",
        json={"content": "Updated Content"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["content"] == "Updated Content"


def test_update_ticket_status(client, auth_headers):
    create_resp = client.post(
        "/tickets/",
        json={"content": "Status Test", "description": "Testing status update"},
        headers=auth_headers,
    )
    ticket_code = create_resp.json()["ticket_code"]

    patch_resp = client.patch(
        f"/tickets/{ticket_code}/status",
        json={"status": "Resolving"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "Resolving"


def test_ticket_user_isolation(client, auth_headers, auth_headers_user_2):
    # User 1 creates a ticket
    create_resp = client.post(
        "/tickets/",
        json={"content": "Private Ticket", "description": "Confidential"},
        headers=auth_headers,
    )
    ticket_code = create_resp.json()["ticket_code"]

    # User 2 tries to read User 1's ticket
    get_resp = client.get(f"/tickets/{ticket_code}", headers=auth_headers_user_2)
    assert get_resp.status_code == 404

    # User 2 tries to update User 1's ticket
    patch_resp = client.patch(
        f"/tickets/{ticket_code}",
        json={"content": "Hacked Content"},
        headers=auth_headers_user_2,
    )
    assert patch_resp.status_code == 404
