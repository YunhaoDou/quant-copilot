"""M4 paper-trading endpoints: accounts, orders, and account snapshots."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import PaperAccount
from app.schemas.paper import AccountCreate, OrderCreate
from app.services import paper_trading
from app.services.paper_trading import OrderError

router = APIRouter(prefix="/paper", tags=["paper-trading"])


def _order_dict(o) -> dict:
    return {
        "id": o.id,
        "symbol": o.ticker_symbol,
        "side": o.side,
        "order_type": o.order_type,
        "quantity": o.quantity,
        "limit_price": o.limit_price,
        "status": o.status,
        "fill_price": o.fill_price,
        "reason": o.reason,
        "created_at": o.created_at,
    }


@router.post("/accounts")
async def create_account(body: AccountCreate, session: AsyncSession = Depends(get_session)):
    try:
        account = await paper_trading.open_account(session, body.name, body.starting_cash)
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": account.id, "name": account.name, "cash_balance": account.cash_balance}


@router.get("/accounts")
async def list_accounts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(PaperAccount).order_by(PaperAccount.id))
    return [
        {"id": a.id, "name": a.name, "starting_cash": a.starting_cash, "cash_balance": a.cash_balance}
        for a in result.scalars()
    ]


@router.get("/accounts/{account_id}")
async def get_account(account_id: int, session: AsyncSession = Depends(get_session)):
    try:
        return await paper_trading.account_snapshot(session, account_id)
    except OrderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/orders")
async def place_order(
    account_id: int, body: OrderCreate, session: AsyncSession = Depends(get_session)
):
    try:
        order = await paper_trading.place_order(
            session,
            account_id,
            body.symbol,
            body.side,
            body.quantity,
            order_type=body.order_type,
            limit_price=body.limit_price,
        )
    except OrderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _order_dict(order)


@router.get("/accounts/{account_id}/orders")
async def list_orders(account_id: int, session: AsyncSession = Depends(get_session)):
    try:
        orders = await paper_trading.list_orders(session, account_id)
    except OrderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_order_dict(o) for o in orders]
