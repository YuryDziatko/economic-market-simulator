from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from econ_sim import (
    POLICY_FIELDS, POLICY_LIMITS, STRUCTURAL_FIELDS,
    PolicyAction, SimulationConfig, agent_catalog, get_agent, compare_scenarios, run_simulation,
)

from .reports import (
    comparison_csv_zip_bytes, comparison_xlsx_bytes,
    simulation_csv_zip_bytes, simulation_xlsx_bytes,
)
from .schemas import AgentSimulationRequest, CompareRequest, PolicySimulationRequest, SimulationRequest


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




@router.get("/policy/limits")
def policy_limits() -> dict[str, Any]:
    return {
        "policy_fields": sorted(POLICY_FIELDS),
        "structural_fields": sorted(STRUCTURAL_FIELDS),
        "limits": {
            name: {
                "minimum": limits.minimum,
                "maximum": limits.maximum,
                "max_annual_change": limits.max_annual_change,
            }
            for name, limits in POLICY_LIMITS.items()
        },
        "action_semantics": "All PolicyAction numeric values are annual deltas, not target levels.",
    }




@router.get("/policy/agents")
def deterministic_agents() -> dict[str, Any]:
    return {
        "agents": agent_catalog(),
        "decision_frequency": "annual",
        "first_decision_year": 2,
        "note": "These are stylized deterministic policy strategies, not empirical descriptions of real governments.",
    }


@router.post("/policy/agents/simulate")
def deterministic_agent_simulate(request: AgentSimulationRequest) -> dict[str, Any]:
    try:
        config = load_baseline_config().with_overrides(**request.overrides)
        agent = get_agent(request.agent)
        result = run_simulation(
            config,
            settings_path=SETTINGS_PATH,
            product_path=PRODUCT_PATH,
            save=False,
            policy_agent=agent,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Deterministic agent simulation failed") from exc

    payload: dict[str, Any] = {
        "agent": {
            "key": agent.key,
            "name": agent.name,
            "profile": next(item for item in agent_catalog() if item["key"] == agent.key),
        },
        "config": config.to_dict(),
        "summary": result.summary(),
        "yearly": _records(result.yearly_summary),
        "policy_history": _records(result.policy_history),
    }
    if request.include_monthly:
        payload["monthly"] = _records(result.monthly_macro)
    return payload


@router.post("/policy/simulate")
def policy_simulate_endpoint(request: PolicySimulationRequest) -> dict[str, Any]:
    try:
        config = load_baseline_config().with_overrides(**request.overrides)
        schedule = {
            int(year): PolicyAction(**action.model_dump())
            for year, action in request.policy_schedule.items()
        }
        result = run_simulation(
            config,
            settings_path=SETTINGS_PATH,
            product_path=PRODUCT_PATH,
            save=False,
            policy_schedule=schedule,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Policy simulation failed") from exc

    payload: dict[str, Any] = {
        "config": config.to_dict(),
        "summary": result.summary(),
        "yearly": _records(result.yearly_summary),
        "policy_history": _records(result.policy_history),
    }
    if request.include_monthly:
        payload["monthly"] = _records(result.monthly_macro)
    return payload


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



def _simulation_result(request: SimulationRequest):
    config = load_baseline_config().with_overrides(**request.overrides)
    return run_simulation(
        config,
        settings_path=SETTINGS_PATH,
        product_path=PRODUCT_PATH,
        save=False,
    )


def _comparison_result(request: CompareRequest):
    baseline = load_baseline_config().with_overrides(**request.baseline_overrides)
    return compare_scenarios(
        baseline,
        request.scenarios,
        baseline_name=request.baseline_name,
        settings_path=SETTINGS_PATH,
        product_path=PRODUCT_PATH,
    )


@router.post("/reports/simulation.xlsx")
def simulation_excel_report(request: SimulationRequest) -> Response:
    try:
        payload = simulation_xlsx_bytes(_simulation_result(request))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create simulation Excel report") from exc
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="economic_simulation_report.xlsx"'},
    )


@router.post("/reports/simulation.zip")
def simulation_csv_report(request: SimulationRequest) -> Response:
    try:
        payload = simulation_csv_zip_bytes(_simulation_result(request))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create simulation CSV report") from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="economic_simulation_csv.zip"'},
    )


@router.post("/reports/comparison.xlsx")
def comparison_excel_report(request: CompareRequest) -> Response:
    try:
        payload = comparison_xlsx_bytes(_comparison_result(request))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create comparison Excel report") from exc
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="economic_scenario_comparison.xlsx"'},
    )


@router.post("/reports/comparison.zip")
def comparison_csv_report(request: CompareRequest) -> Response:
    try:
        payload = comparison_csv_zip_bytes(_comparison_result(request))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not create comparison CSV report") from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="economic_scenario_comparison_csv.zip"'},
    )
