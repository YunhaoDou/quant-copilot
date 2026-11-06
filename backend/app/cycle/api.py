"""可独立启动的离线研究 API，无需数据库和 Redis。"""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.cycle.engine import event_study, load_config, snapshots
from app.cycle.providers import AkShareDataProvider, CSVDataProvider, MockDataProvider
from app.cycle.live import live_dashboard
from app.cycle.market import router as market_router

router = APIRouter(prefix="/cycle", tags=["情绪周期"])


@router.get("")
def dashboard(source: Literal["mock", "csv", "akshare"] = "akshare", as_of: str | None = None, pattern: str = "启动龙头", horizon: int = 2):
    try:
        config = load_config()
        if horizon not in config["backtest_forward_days"]:
            raise ValueError("持有期限不在配置列表中")
        if source == "akshare":
            return live_dashboard(config, as_of)
        provider = MockDataProvider(config["mock_seed"], config["mock_days"]) if source == "mock" else CSVDataProvider(Path(__file__).resolve().parents[2] / "data" / "cycle") if source == "csv" else AkShareDataProvider()
        frame = provider.daily()
        as_of = as_of or "2026-12-31"
        cutoff = as_of + "T15:00:00+08:00" if len(as_of) == 10 else as_of
        history = snapshots(frame, cutoff, config)
        intraday = provider.intraday(history[-1]["date"]) if history else None
        if intraday is not None and not intraday.empty:
            import pandas as pd
            intraday = intraday[pd.to_datetime(intraday.available_at, utc=True) <= pd.Timestamp(cutoff)]
        # 回放日期之后的数据不可进入任何统计。
        visible = frame[frame.date <= (history[-1]["date"] if history else "")]
        return dict(source=source, simulated=source == "mock", config=config, dates=sorted(frame.date.unique()), history=history, current=history[-1] if history else None, intraday=[] if intraday is None else intraday.to_dict("records"), backtest=event_study(visible, history, config, pattern, horizon))
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="真实行情请求失败，请稍后重试：" + str(exc)[:160]) from exc


app = FastAPI(title="情绪周期离线研究服务")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], allow_methods=["GET"])
app.include_router(router)
app.include_router(market_router)
