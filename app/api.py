from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException

from econ_sim import SimulationConfig, compare_scenarios, run_simulation

from .schemas import CompareRequest, SimulationRequest


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SETTINGS_PATH = DATA_DIR / "Simulation_Settings.xlsx"
PRODUCT_PATH = DATA_DIR / "Product_List.xlsx"

router = APIRouter(prefix="/api", tags=["simulation"])


def load_baseline_config() -> SimulationConfig:
    return SimulationConfig.from_excel(SETTINGS_PATH)


def _records(frame) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return frame.replace({np.nan: None}).to_dict(orient="records")


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "economic-market-simulator",
        "api_version": "1.0",
    }


@router.get("/config")
def get_config() -> dict[str, Any]:
    config = load_baseline_config()
    return {
        "defaults": config.to_dict(),
        "source": "data/Simulation_Settings.xlsx",
    }


@router.post("/simulate")
def simulate_endpoint(request: SimulationRequest) -> dict[str, Any]:
    try:
        config = load_baseline_config().with_overrides(**request.overrides)
        result = run_simulation(
            config,
            settings_path=SETTINGS_PATH,
            product_path=PRODUCT_PATH,
            save=False,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # keep internal details out of the public response
        raise HTTPException(status_code=500, detail="Simulation failed") from exc

    payload: dict[str, Any] = {
        "config": config.to_dict(),
        "summary": result.summary(),
        "yearly": _records(result.yearly_summary),
    }
    if request.include_monthly:
        payload["monthly"] = _records(result.monthly_macro)
    return payload


@router.post("/compare")
def compare_endpoint(request: CompareRequest) -> dict[str, Any]:
    try:
        baseline = load_baseline_config().with_overrides(**request.baseline_overrides)
        comparison = compare_scenarios(
            baseline,
            request.scenarios,
            baseline_name=request.baseline_name,
            settings_path=SETTINGS_PATH,
            product_path=PRODUCT_PATH,
        )
        return comparison.to_dict()
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Scenario comparison failed") from exc
