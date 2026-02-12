from server import api
from fastapi.testclient import TestClient

client = TestClient(api)

def test_evaluate_document():
    response = client.post(
        "/evaluate",
        files={"document": ("dummy.txt", b"dummy content", "text/plain")},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "dummy.txt evaluated successfully"}