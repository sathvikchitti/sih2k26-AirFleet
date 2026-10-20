"""FastAPI backend — React -> FastAPI -> (ML service / engines) -> repositories.

Production path: replace `app/repositories` with PostgreSQL + SQLAlchemy and
swap `app/services/ml` internals for the real model. Neither the service layer
nor the API contract has to change.

Legacy endpoints from the original POC are preserved byte-for-byte in shape
and are now projections of the new model (see services/compatibility.py).
"""

import logging
import math
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi import Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder

from . import routers
from .repositories import reset as reset_repositories, store as repository_store
from .services import audit_service
from .services.availability_service import sync_aircraft_states
from .services.ml import PredictionValidationError
from .services.maintenance_service import MaintenanceTransitionError, ingest_prediction
from .domain.enums import Permission
from .security import (require_demo_permission, reset_enabled,
                       validate_permission_config)
from .access import evaluator_access, frontend_origins, validate_access_config

app = FastAPI(title="Aircraft Fleet Readiness & Sustainment API", version="0.2.0")

# Reject typos during startup rather than silently selecting a weaker mode.
validate_permission_config()
validate_access_config()


@app.exception_handler(PredictionValidationError)
async def prediction_unavailable(_request: Request, exc: PredictionValidationError):
    # Keep provider diagnostics in server logs only. Loader exceptions may
    # contain local artifact/data paths, which must not become API output.
    cause = exc.__cause__
    if cause is not None:
        logging.getLogger(__name__).error(
            "ML prediction unavailable (%s): %s",
            type(cause).__name__, cause,
            exc_info=(type(cause), cause, cause.__traceback__),
        )
    else:
        logging.getLogger(__name__).error("ML prediction unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "prediction provider unavailable",
            "prediction_status": "unavailable",
        },
    )


@app.exception_handler(MaintenanceTransitionError)
async def maintenance_transition_conflict(_request: Request, exc: MaintenanceTransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def _json_safe_validation_value(value):
    """Keep standard 422 details serializable when clients send NaN/Infinity."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe_validation_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_validation_value(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError):
    # FastAPI's default encoder preserves non-finite values inside `input`,
    # which Starlette's strict JSONResponse rejects. Retain its 422/detail
    # contract while replacing only those unserializable values.
    details = _json_safe_validation_value(jsonable_encoder(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": details})

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(evaluator_access)


@app.get("/livez", include_in_schema=False)
def liveness():
    return {"ok": True}


@app.get("/login", include_in_schema=False)
def evaluator_login():
    # A top-level browser challenge caches Basic credentials for this origin.
    # The same-origin frontend proxy forwards subsequent Authorization headers.
    return RedirectResponse("/", status_code=303)

def initialize_demo_state() -> None:
    """Initialize provider-consistent demo state for the selected ML source.

    The deterministic workflow seed contains mock-derived events and work
    orders. When FD001 is explicitly selected, retaining those records beside
    real-model predictions would falsely attribute a subsystem and flight-hour
    deadline to RUL-only data. Keep the aircraft/inventory catalog, clear those
    operational seed records, then ingest fresh FD001 predictions.
    """
    selected_provider = os.getenv("ML_PROVIDER", "mock").strip().lower()
    selected_scenario = os.getenv("DEMO_SCENARIO", "").strip().lower()
    if selected_scenario not in {"", "fd001_operations"}:
        raise RuntimeError(
            f"unsupported DEMO_SCENARIO {selected_scenario!r}; choose 'fd001_operations' or leave unset"
        )
    if selected_scenario == "fd001_operations" and selected_provider != "fd001":
        raise RuntimeError("DEMO_SCENARIO=fd001_operations requires ML_PROVIDER=fd001")
    if selected_scenario == "fd001_operations":
        # Validate selected real provider before clearing or mutating state.
        from .services.ml import get_provider
        get_provider()
    if selected_provider == "fd001":
        reset_repositories()
        state = repository_store()
        state["work_orders"] = []
        state["predicted_events"] = []
        state["transfers"] = []
        state["prediction_history"] = []
        state["audit"] = []
        state["work_order_seq"] = 1046
        state["event_seq"] = 1
        state["transfer_seq"] = 103
        state["audit_seq"] = 1
        try:
            for aircraft in state["aircraft"]:
                ingest_prediction(aircraft["id"])
        except PredictionValidationError as exc:
            # Explicit provider selection remains unavailable; never replace
            # it with mock predictions. Empty histories/events are accurate.
            logging.getLogger(__name__).warning(
                "FD001 provider unavailable during demo initialization: %s", exc
            )
    else:
        reset_repositories()
    try:
        sync_aircraft_states()
    except PredictionValidationError as exc:
        # Keep the API startable if an explicitly selected model is missing.
        # Prediction routes return the standard 503/unavailable response.
        logging.getLogger(__name__).warning("ML provider unavailable during startup: %s", exc)
    if selected_scenario == "fd001_operations":
        from .services.fd001_operations_scenario import initialize_fd001_operations_scenario
        initialize_fd001_operations_scenario()


initialize_demo_state()

app.include_router(routers.health.router)
app.include_router(routers.aircraft.router)
app.include_router(routers.bases.router)
app.include_router(routers.evaluation.router)
app.include_router(routers.inventory.router)
app.include_router(routers.maintenance.router)
app.include_router(routers.transfers.router)
app.include_router(routers.recommendations.router)
app.include_router(routers.audit.router)


# --------------------------------------------------------------------------
# Demo control. Everything else lives in app/routers/*.
# --------------------------------------------------------------------------
@app.get("/api/demo/scenario")
def demo_scenario():
    """Describe the selected synthetic scenario; operational values remain API-backed."""
    from .services.fd001_operations_scenario import scenario_manifest
    return scenario_manifest()


@app.post("/api/demo/reset")
def demo_reset(demo_role: str | None = Header(None, alias="X-Demo-Role"),
               demo_base: str | None = Header(None, alias="X-Demo-Base")):
    """Restore the deterministic demo dataset."""
    if not reset_enabled():
        raise HTTPException(status_code=403, detail="demo reset is disabled")
    require_demo_permission("commander", Permission.APPROVE_RECOMMENDATION,
                            demo_role=demo_role, demo_base=demo_base)
    initialize_demo_state()
    audit_service.demo_reset()
    return {"ok": True}
