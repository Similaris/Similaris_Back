def test_validation_errors_have_a_stable_contract(client):
    response = client.post("/api/auth/login", json={"email": "invalid", "password": "x"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["detail"] == "Os dados enviados são inválidos."
    assert response.json()["errors"]


def test_http_errors_have_a_stable_contract(client):
    response = client.get("/api/documents/999/segments")

    assert response.status_code == 404
    assert response.json() == {
        "code": "http_404",
        "detail": "Documento não encontrado.",
    }
