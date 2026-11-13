"""Initialize the month-long systematic simulation (run once).

Ingests full history for the universe + SPY, creates the four strategy accounts and the
SPY buy-and-hold benchmark, and takes the first walk-forward step (day 0).

Usage (from backend/, venv active, backend/.env present):
    python -m scripts.init_sim              # default $1,000 starting cash per account
    python -m scripts.init_sim 5000         # custom starting cash
"""
import asyncio
import sys
from datetime import date

from app.db.session import AsyncSessionLocal
from app.services import data_ingestion, sim


async def _main(starting_cash: float) -> None:
    universe = sim.SIM_UNIVERSE + [sim.BENCHMARK_SYMBOL]
    async with AsyncSessionLocal() as session:
        print(f"Ingesting {len(universe)} symbols...")
        for symbol in universe:
            try:
                n = await data_ingestion.ingest_ticker(session, symbol, symbol, start="20200101")
                print(f"  {symbol:6s} {n} bars")
            except Exception as exc:
                print(f"  ! {symbol} ingest failed: {exc}")

        result = await sim.init_sim(session, starting_cash=starting_cash)
        print(f"\nCreated accounts: {result['created'] or '(all already existed)'}")
        print(f"Starting cash per account: ${starting_cash:,.0f}")

        out = await sim.run_sim_day(session, on_date=date.today())
        print(f"\nDay 0 ({out['date']}) executed. {len(out['actions'])} opening trades.")
        print("From now on, run `python -m scripts.run_sim_day` once per trading day.")


if __name__ == "__main__":
    cash = float(sys.argv[1]) if len(sys.argv) > 1 else 1000.0
    asyncio.run(_main(cash))
