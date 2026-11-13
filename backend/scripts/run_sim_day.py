"""Advance the systematic simulation by one trading day.

Run this once per US trading day (after the close). It:
  1. ingests the latest daily bars for the sim universe + SPY (yfinance),
  2. reconciles each strategy account to its current signal and logs equity,
  3. prints the day's actions and a standings table vs the SPY benchmark.

Usage (from backend/, with the venv active and backend/.env present):
    python -m scripts.run_sim_day
"""
import asyncio
from datetime import date

from app.db.session import AsyncSessionLocal
from app.services import data_ingestion, sim


async def _main() -> None:
    universe = sim.SIM_UNIVERSE + [sim.BENCHMARK_SYMBOL]
    async with AsyncSessionLocal() as session:
        # 1. refresh prices (idempotent upsert; pulls whatever is new since last run)
        for symbol in universe:
            try:
                await data_ingestion.ingest_ticker(session, symbol, symbol, start="20200101")
            except Exception as exc:  # network hiccup on one name shouldn't abort the day
                print(f"  ! {symbol} ingest failed: {exc}")

        # 2. walk forward one day
        out = await sim.run_sim_day(session, on_date=date.today())
        print(f"\n=== Sim day {out['date']} ===")
        if out["actions"]:
            for a in out["actions"]:
                print(f"  {a['account']:24s} {a['action']:4s} {a['symbol']:6s} [{a['status']}]")
        else:
            print("  (no position changes today)")

        # 3. standings
        report = await sim.sim_report(session)
        bench = report["benchmark"]
        print("\n--- Standings (total return %) ---")
        if bench:
            print(f"  {'BENCHMARK ' + bench['account']:30s} {bench['total_return_pct']:+7.2f}%  "
                  f"({bench['days_logged']}d)")
        for s in report["strategies"]:
            vs = f"{s['vs_spy_pct']:+.2f}% vs SPY" if s["vs_spy_pct"] is not None else ""
            print(f"  {s['account']:30s} {s['total_return_pct']:+7.2f}%  {vs}")


if __name__ == "__main__":
    asyncio.run(_main())
