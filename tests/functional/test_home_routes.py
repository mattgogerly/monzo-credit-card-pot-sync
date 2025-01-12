def test_home_get_contains_jumbotron(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Simplify Your Spend" in response.data


def test_home_post_invalid_method(test_client):
    response = test_client.post("/")
    assert response.status_code == 405
