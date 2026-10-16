"""
Treasury par-yield data, shock scenarios and illustrative zero-coupon risk.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, FiniteFloat
from typing import Annotated, Dict, Literal, Optional
import math
from backend.curve import (
    get_curve,
    get_curve_status,
    apply_parallel_shock,
    apply_steepener,
    apply_custom_shock
)
from backend.bond import calculate_duration, calculate_dv01

app = FastAPI(title="US Treasury Rates Change Simulator")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    """Request model for scenario analysis"""
    type: Literal['parallel', 'steepener', 'custom']
    magnitude: FiniteFloat = 0  # Shock magnitude in bps
    pivot: Annotated[FiniteFloat, Field(gt=0)] = 2.0
    custom_shocks: Optional[Dict[Annotated[FiniteFloat, Field(gt=0)], FiniteFloat]] = None


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    # Echoing an overflowing JSON number (e.g. 1e309) makes error JSON invalid.
    details = [{key: error[key] for key in ('loc', 'msg', 'type')}
               for error in exc.errors()]
    return JSONResponse(status_code=422, content={'detail': details})


@app.get("/")
async def root():
    """Check the process, without fetching or validating Treasury data."""
    return {
        "service": "US Treasury Rates Change Simulator",
        "status": "operational",
        "version": "1.0"
    }


@app.post("/api/analyze")
def analyze_scenario(request: AnalyzeRequest):
    """
    Analyze a yield curve scenario with specified shock.
    
    Returns original curve, shocked curve, and key metrics.
    """
    try:
        # Get base curve
        date, original_curve = get_curve()
        if not original_curve:
            raise ValueError('No usable Treasury yields.')
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Treasury data unavailable: {str(e)}"
        )
    
    try:
        if request.type == "parallel":
            shocked_curve = apply_parallel_shock(original_curve, request.magnitude)
        elif request.type == "steepener":
            shocked_curve = apply_steepener(original_curve, request.magnitude, request.pivot)
        else:
            custom_shocks = request.custom_shocks or {}
            missing = [tenor for tenor, shock in custom_shocks.items()
                       if shock != 0 and tenor not in original_curve]
            if missing:
                raise ValueError(f'No Treasury observation for requested tenors: {missing}')
            shocked_curve = apply_custom_shock(original_curve, custom_shocks)

        metrics = {}
        for tenor, orig_yield in original_curve.items():
            shock_yield = shocked_curve[tenor]
            metric = {
                "yield": shock_yield,
                "delta_bps": (shock_yield - orig_yield) * 100,
                "duration": calculate_duration(shock_yield, tenor),
                "dv01": calculate_dv01(shock_yield, tenor),
            }
            if not all(math.isfinite(value) for value in metric.values()):
                raise ValueError('Scenario exceeds the numerical range of the risk model.')
            metrics[tenor] = metric
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    
    return {
        "date": date,
        "original_curve": original_curve,
        "shocked_curve": shocked_curve,
        "metrics": metrics,
        "data_status": get_curve_status(),
        "risk_model": {
            "instrument": "illustrative zero-coupon bond",
            "compounding": "annual",
            "face_value_usd": 100,
            "yield_input": "Treasury par yield used as a proxy, not a bootstrapped spot rate",
            "duration_unit": "years",
            "dv01_unit": "USD per basis point per $100 face value",
        },
    }


@app.get("/api/curve")
def get_current_curve():
    """
    Get the current US Treasury yield curve.
    
    Returns the latest yield curve data with date.
    """
    try:
        date, curve = get_curve()
        if not curve:
            raise ValueError('No usable Treasury yields.')
        return {
            "date": date,
            "curve": curve,
            "data_status": get_curve_status(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Treasury data unavailable: {str(e)}"
        )
