"""Celery task: the earnings pipeline (SEC monitor -> filing parser -> report generator).

Pure file-I/O, no Postgres/SQLAlchemy involved (unlike backtest_tasks.py), so this
task runs synchronously — no async engine/session needed.
"""
import time
from datetime import datetime

from app.services.earnings import filing_parser, paths as cfg, report_generator, sec_monitor
from app.tasks.celery_app import celery_app


def _run_pipeline() -> dict:
    """Run the complete earnings pipeline. Ported from earnings-bot/scripts/orchestrator.py."""
    start_time = datetime.now()
    cfg.logger.info(f"{'='*60}")
    cfg.logger.info(f"EARNINGS PIPELINE STARTED at {start_time.isoformat()}")
    cfg.logger.info(f"{'='*60}")

    results = {
        "started_at": start_time.isoformat(),
        "completed_at": "",
        "new_filings_found": 0,
        "filings_processed": 0,
        "reports_generated": 0,
        "errors": [],
        "summary": "",
    }

    # Step 1: Monitor SEC for new filings
    cfg.logger.info("\n[Step 1/3] SEC Monitor - Scanning for new filings...")
    try:
        new_filings = sec_monitor.find_new_filings(
            form_types=["10-K", "10-Q", "8-K"],
            lookback_hours=14,
        )
        results["new_filings_found"] = len(new_filings)

        if new_filings:
            sec_monitor.save_pending_filings(new_filings)
            cfg.logger.info(f"Found {len(new_filings)} new filings from watchlist companies.")
            for f in new_filings:
                cfg.logger.info(f"  [{f['form_type']:>5s}] {f['ticker']:6s} {f['company_name'][:40]}")
        else:
            cfg.logger.info("No new filings found.")
            results["summary"] = "No new filings from watchlist companies in the past 12 hours."
            return results
    except Exception as e:
        cfg.logger.error(f"Step 1 failed: {e}")
        results["errors"].append(f"SEC Monitor: {e}")
        return results

    time.sleep(1)

    # Step 2: Download and parse filings
    cfg.logger.info("\n[Step 2/3] Filing Parser - Downloading and parsing filings...")
    try:
        processed = filing_parser.process_pending_filings()
        results["filings_processed"] = len(processed)

        completed = [p for p in processed if p.get("status") == "completed"]
        failed = [p for p in processed if p.get("status") == "error"]

        cfg.logger.info(f"Processed: {len(completed)} completed, {len(failed)} failed")
        for f in failed:
            cfg.logger.warning(f"  ✗ {f['ticker']}: {f.get('error', 'unknown error')}")
    except Exception as e:
        cfg.logger.error(f"Step 2 failed: {e}")
        results["errors"].append(f"Filing Parser: {e}")
        return results

    time.sleep(1)

    # Step 3: Generate reports
    cfg.logger.info("\n[Step 3/3] Report Generator - Creating analysis reports...")
    try:
        reports = report_generator.run()
        results["reports_generated"] = len(reports)
        for r in reports:
            cfg.logger.info(f"  ✓ Report: {r['ticker']} -> {r['report_path']}")
    except Exception as e:
        cfg.logger.error(f"Step 3 failed: {e}")
        results["errors"].append(f"Report Generator: {e}")

    end_time = datetime.now()
    results["completed_at"] = end_time.isoformat()
    duration = (end_time - start_time).total_seconds()

    summary_parts = []
    if results["new_filings_found"] > 0:
        summary_parts.append(f"发现 {results['new_filings_found']} 份新申报")
    if results["reports_generated"] > 0:
        summary_parts.append(f"生成 {results['reports_generated']} 份财报分析报告")
    if results["errors"]:
        summary_parts.append(f"出现 {len(results['errors'])} 个错误")

    results["summary"] = " | ".join(summary_parts) if summary_parts else "无新财报发布"
    results["duration_seconds"] = round(duration, 1)

    cfg.logger.info(f"\n{'='*60}")
    cfg.logger.info(f"PIPELINE COMPLETED in {duration:.1f}s")
    cfg.logger.info(f"Results: {results['summary']}")
    cfg.logger.info(f"{'='*60}")

    return results


@celery_app.task(name="run_earnings_pipeline")
def run_earnings_pipeline_task() -> dict:
    return _run_pipeline()
