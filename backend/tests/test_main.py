from fastapi.testclient import TestClient
from main import app, sanitize_pii

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_pii_sanitization():
    raw_text = "Contact me at john.doe@example.com or call 555-019-2834."
    cleaned = sanitize_pii(raw_text)
    assert "john.doe@example.com" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned
    assert "[REDACTED_PHONE]" in cleaned

def test_extract_payload_validation_failure():
    response = client.post(
        "/api/v1/jobs/not-a-real-job/candidates",
        json={
            "display_name": "Test Candidate",
            "resume_text": "Short",
            "consent_acknowledged": True,
        },
    )
    assert response.status_code == 422
