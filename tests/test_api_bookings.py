def test_create_and_get_booking(client, auth_headers):
    payload = {
        "reason": "Quarterly Review",
        "time": "2026-09-15 10:00",
        "note": "Need large monitor",
        "customer_name": "Dave",
        "customer_phone": "0987111222",
        "email": "dave@example.com",
    }
    create_resp = client.post("/bookings/", json=payload, headers=auth_headers)
    assert create_resp.status_code == 200
    booking_data = create_resp.json()
    assert booking_data["reason"] == "Quarterly Review"
    assert booking_data["status"] == "Scheduled"
    booking_code = booking_data["booking_code"]

    get_resp = client.get(f"/bookings/{booking_code}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["booking_code"] == booking_code


def test_list_bookings(client, auth_headers):
    for i in range(2):
        client.post(
            "/bookings/",
            json={"reason": f"Meeting {i}", "time": f"2026-09-{10+i} 09:00"},
            headers=auth_headers,
        )

    resp = client.get("/bookings/", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_update_booking(client, auth_headers):
    create_resp = client.post(
        "/bookings/",
        json={"reason": "Original Reason", "time": "2026-09-20 14:00"},
        headers=auth_headers,
    )
    booking_code = create_resp.json()["booking_code"]

    patch_resp = client.patch(
        f"/bookings/{booking_code}",
        json={"reason": "Updated Reason"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["reason"] == "Updated Reason"


def test_cancel_booking(client, auth_headers):
    create_resp = client.post(
        "/bookings/",
        json={"reason": "To be canceled", "time": "2026-09-21 15:00"},
        headers=auth_headers,
    )
    booking_code = create_resp.json()["booking_code"]

    cancel_resp = client.post(f"/bookings/{booking_code}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "Canceled"


def test_booking_user_isolation(client, auth_headers, auth_headers_user_2):
    create_resp = client.post(
        "/bookings/",
        json={"reason": "Confidential Meeting", "time": "2026-09-22 10:00"},
        headers=auth_headers,
    )
    booking_code = create_resp.json()["booking_code"]

    # User 2 cannot access
    get_resp = client.get(f"/bookings/{booking_code}", headers=auth_headers_user_2)
    assert get_resp.status_code == 404

    # User 2 cannot cancel
    cancel_resp = client.post(f"/bookings/{booking_code}/cancel", headers=auth_headers_user_2)
    assert cancel_resp.status_code == 404
