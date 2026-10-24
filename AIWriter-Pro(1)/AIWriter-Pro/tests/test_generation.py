def test_generate_requires_login(client):
    response = client.post("/generate", data={"prompt": "hello"})
    assert response.status_code == 302
