from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import app
from src.data.load_data import load_truth

client = TestClient(app)
PDF = Path(__file__).resolve().parents[1] / "data" / "raw" / "drawings" / "SYN-PID-002.pdf"


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_hazop_from_uploaded_drawing():
    r = client.post("/hazop", files={"file": ("SYN-PID-002.pdf", PDF.read_bytes(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    truth = load_truth("SYN-PID-002")
    assert set(body["read"]["equipment"]) == {e["tag"] for e in truth["equipment"]}
    assert body["hazop_rows"] and {"deviation", "causes", "safeguards_on_drawing"} <= set(body["hazop_rows"][0])


def test_rejects_non_pdf():
    assert client.post("/hazop", files={"file": ("x.txt", b"hello", "text/plain")}).status_code == 422
