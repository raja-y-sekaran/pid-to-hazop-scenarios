"""FastAPI service: upload one vector-PDF P&ID, get back what was read and a draft HAZOP worksheet.

    uvicorn src.api.app:app --reload      # then open http://127.0.0.1:8000/docs
"""
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from src.features.pid_reader import read_pid
from src.hazop.engine import Graph, draft_hazop
from src.pipeline import extracted

app = FastAPI(title="P&ID to HAZOP scenarios", version="1.0",
              description="Reads vector-PDF P&IDs drawn to this project's conventions. Synthetic-data demo; "
                          "the output is a draft for a HAZOP team, not a HAZOP.")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/hazop")
async def hazop(file: UploadFile = File(..., description="Vector PDF P&ID")):
    data = await file.read()
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "expected a PDF file")
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / (Path(file.filename or "drawing.pdf").stem + ".pdf")
        pdf.write_bytes(data)
        try:
            m = read_pid(pdf)
        except Exception as e:  # a PDF that is not a readable vector drawing
            raise HTTPException(422, f"could not read the drawing: {e}") from e
    rows = draft_hazop(Graph.from_model(m))
    return dict(read=extracted(m), hazop_rows=[r.as_dict() for r in rows],
                gaps=sum(bool(r.gap) for r in rows))
