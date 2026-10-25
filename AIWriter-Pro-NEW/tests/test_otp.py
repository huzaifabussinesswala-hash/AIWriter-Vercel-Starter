def test_verify_requires_pending_signup(client):
    response = client.get("/verify-email")
    assert response.status_code == 302
