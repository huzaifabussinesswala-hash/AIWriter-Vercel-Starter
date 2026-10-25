def test_signup_validates_password(client):
    response = client.post("/signup", data={
        "name": "Test User", "email": "test@example.com",
        "password": "short", "confirm_password": "short"
    }, follow_redirects=True)
    assert b"at least 8 characters" in response.data

def test_login_rejects_unknown_user(client):
    response = client.post("/login", data={"email": "none@example.com", "password": "wrong"}, follow_redirects=True)
    assert b"incorrect" in response.data
