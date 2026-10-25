def test_home_and_plans(client):
    assert client.get("/").status_code == 200
    assert client.get("/plans").status_code == 200

def test_dashboard_requires_login(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_health(client):
    assert client.get("/health").status_code in (200, 503)
