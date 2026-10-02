"""Macro-regime asset-allocation endpoint: a market-wide read, not per-ticker."""
from fastapi import APIRouter, HTTPException

from app.services import asset_allocation

router = APIRouter(prefix="/allocation", tags=["asset_allocation"])


@router.get("")
def get_allocation():
    try:
        return asset_allocation.get_asset_allocation()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
