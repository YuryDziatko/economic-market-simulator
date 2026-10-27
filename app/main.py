from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import router as api_router


ROOT = Path(__file__).resolve().parents[1]

app = FastAPI(
    title="Economic Market Simulator API",
    description=(
        "Run configurable economic simulations and compare policy scenarios. "
        "The economics engine is exposed through SimulationConfig and run_simulation()."
    ),
    version="0.3.0",
)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Economic Market Simulator"},
    )
