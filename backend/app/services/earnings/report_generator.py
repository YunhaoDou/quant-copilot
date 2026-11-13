#!/usr/bin/env python3
"""
Report Generator — Financial Analysis & Chinese Summary Report.

Takes processed filing data (JSON from filing_parser.py), performs
quantitative analysis, and generates a structured Markdown report.
The narrative sections (🔥热点, ✨亮点, 👍优点, ⚠️风险) are drafted
with data-driven observations for the LLM to polish.
"""
import json
from datetime import datetime

from . import paths as cfg


def load_processed_filings() -> list[dict]:
    """Load the most recent batch of processed filings."""
    processed_dir = cfg.TODAY_DIR / "processed"
    if not processed_dir.exists():
        return []

    files = sorted(processed_dir.glob("all_*.json"))
    if not files:
        # Load individual filing files
        result = []
        for f in sorted(processed_dir.glob("*_10-*.json"))[-20:]:
            try:
                with open(f) as fh:
                    result.append(json.load(fh))
            except Exception:
                pass
        return result

    with open(files[-1]) as f:
        return json.load(f)


def format_currency(val, unit: str = "auto") -> str:
    """Format a number as currency with appropriate unit."""
    if val is None:
        return "N/A"
    if unit == "auto":
        abs_val = abs(val)
        if abs_val >= 1_000_000_000_000:
            return f"${val / 1_000_000_000_000:.2f}T"
        elif abs_val >= 1_000_000_000:
            return f"${val / 1_000_000_000:.2f}B"
        elif abs_val >= 1_000_000:
            return f"${val / 1_000_000:.2f}M"
        elif abs_val >= 1_000:
            return f"${val / 1_000:.2f}K"
        else:
            return f"${val:.2f}"
    return f"${val:,}"


def get_metric_value(statement: dict, metric: str) -> tuple:
    """Get the latest and previous value for a metric from financial data."""
    values = statement.get(metric, [])
    if not values:
        return None, None
    return values[0].get("val"), values[1].get("val") if len(values) > 1 else None


def compute_yoy_change(current, previous) -> float | None:
    """Compute YoY percentage change."""
    if current is not None and previous is not None and previous != 0:
        return round((current - previous) / abs(previous) * 100, 2)
    return None


def generate_financial_analysis(processed: dict) -> dict:
    """
    Perform comprehensive financial analysis on a single filing.
    Returns structured analysis data for the report.
    """
    fin = processed.get("financial_summary", {})
    is_ = fin.get("income_statement", {})
    bs = fin.get("balance_sheet", {})
    cf = fin.get("cash_flow", {})
    ratios = fin.get("ratios", {})
    mda = processed.get("mda", {})

    analysis = {
        "ticker": processed.get("ticker", ""),
        "company_name": "",  # Will be filled from companies lookup
        "form_type": processed.get("form_type", ""),
        "filing_date": processed.get("filing_date", "")[:10],
        "key_metrics_table": [],
        "anomalies": [],
        "cross_validation": {},
        "highlights": [],
        "risk_factors": [],
        "strengths": [],
        "mda_summary": "",
    }

    # --- Key Metrics Table ---
    metrics = [
        ("营收", "revenue", "B"),
        ("毛利润", "gross_profit", "B"),
        ("营业利润", "operating_income", "B"),
        ("净利润", "net_income", "B"),
        ("经营现金流", "operating_cash_flow", "B"),
        ("自由现金流", None, "B"),  # special case
        ("毛利率", "gross_margin", "pct"),
        ("净利率", "net_margin", "pct"),
        ("营业利润率", "operating_margin", "pct"),
        ("ROE", "roe", "pct"),
        ("经营活动现金流/净利润", "ocf_to_ni", "x"),
        ("总资产", "total_assets", "B"),
        ("总负债", "total_liabilities", "B"),
        ("股东权益", "total_equity", "B"),
        ("现金及等价物", "cash_and_equivalents", "B"),
        ("长期债务", "long_term_debt", "B"),
    ]

    table_rows = []
    for label, key, metric_type in metrics:
        if key is None:
            # Special handling for FCF
            fcf = ratios.get("fcf")
            if fcf:
                val_str = format_currency(fcf)
                yoy = ratios.get("revenue_yoy_change_pct")  # Placeholder - need to compute FCF YoY
                table_rows.append({
                    "指标": label,
                    "本季实际": val_str,
                    "同比变化": f"{yoy:+.1f}%" if yoy else "-",
                })
            continue

        if metric_type == "pct":
            val = ratios.get(key)
            if val is not None:
                table_rows.append({
                    "指标": label,
                    "本季实际": f"{val:.2f}%",
                    "同比变化": "-",
                })
        elif metric_type in ("B", "M", "K"):
            if key in is_:
                val, prev = get_metric_value(is_, key)
            elif key in bs:
                val, prev = get_metric_value(bs, key)
            elif key in cf:
                val, prev = get_metric_value(cf, key)
            else:
                continue

            if val is not None:
                val_str = format_currency(val)
                yoy = compute_yoy_change(val, prev)
                yoy_str = f"{yoy:+.1f}%" if yoy is not None else "-"
                table_rows.append({
                    "指标": label,
                    "本季实际": val_str,
                    "同比变化": yoy_str,
                })
        elif metric_type == "x":
            val = ratios.get(key)
            if val is not None:
                table_rows.append({
                    "指标": label,
                    "本季实际": f"{val:.2f}x",
                    "同比变化": "-",
                })

    analysis["key_metrics_table"] = table_rows

    # --- Cross-validation: Net Income vs Operating Cash Flow ---
    ni = get_metric_value(is_, "net_income")[0]
    ocf = get_metric_value(cf, "operating_cash_flow")[0]
    d_a = get_metric_value(cf, "depreciation_amortization_cf")[0]
    sbc = get_metric_value(cf, "stock_based_comp")[0]

    if ni and ocf:
        diff = ocf - ni
        diff_pct = round(diff / abs(ni) * 100, 2) if ni != 0 else 0
        explanation_parts = []
        if d_a:
            explanation_parts.append(f"折旧摊销 ${format_currency(d_a)}")
        if sbc:
            explanation_parts.append(f"股权激励 ${format_currency(sbc)}")

        analysis["cross_validation"] = {
            "ni": ni,
            "ocf": ocf,
            "diff": diff,
            "diff_pct": diff_pct,
            "ocf_to_ni_ratio": round(ocf / ni, 2) if ni != 0 else 0,
            "status": "✅ 正常" if abs(diff_pct) < 50 else "⚠️ 需关注" if abs(diff_pct) < 100 else "🔴 异常",
            "explanation": f"净利润${format_currency(ni)} vs 经营现金流${format_currency(ocf)}，"
                          f"差异{diff_pct:+.1f}%。" +
                          (f"主要调节项：{', '.join(explanation_parts)}。" if explanation_parts else ""),
        }

    # --- YoY analysis: flag changes > 20% ---
    for statement_label, statement_dict in [("利润表", is_), ("资产负债表", bs), ("现金流量表", cf)]:
        for metric_name, values in statement_dict.items():
            if len(values) >= 2:
                current = values[0]["val"]
                previous = values[1]["val"]
                change = compute_yoy_change(current, previous)
                if change is not None and abs(change) > 20:
                    analysis["anomalies"].append({
                        "statement": statement_label,
                        "metric": metric_name,
                        "change_pct": change,
                        "current": current,
                        "previous": previous,
                        "end_date": values[0]["end_date"],
                    })

    # --- Balance sheet checks ---
    total_assets = get_metric_value(bs, "total_assets")[0]
    total_liab = get_metric_value(bs, "total_liabilities")[0]
    total_eq = get_metric_value(bs, "total_equity")[0]

    if total_assets and total_liab and total_eq:
        calc_eq = total_assets - total_liab
        eq_diff = abs(calc_eq - total_eq) / abs(total_eq) * 100 if total_eq != 0 else 0
        analysis["cross_validation"]["balance_check"] = {
            "assets_liab_equity_diff_pct": round(eq_diff, 4),
            "status": "✅ 平衡" if eq_diff < 0.1 else "⚠️ 有差异",
        }

    # Liability ratio
    if total_assets and total_liab:
        liab_ratio = total_liab / total_assets * 100 if total_assets != 0 else 0
        analysis["risk_factors"].append({
            "type": "资产负债率",
            "detail": f"{liab_ratio:.1f}%",
            "assessment": "偏高" if liab_ratio > 70 else "适中" if liab_ratio > 40 else "偏低",
        })

    # Cash runway check
    cash = get_metric_value(bs, "cash_and_equivalents")[0]
    ocf_val = get_metric_value(cf, "operating_cash_flow")[0]
    if cash and ocf_val and ocf_val > 0:
        months = cash / (ocf_val / 12)
        analysis["strengths"].append({
            "type": "现金充足度",
            "detail": f"现金等价物{format_currency(cash)}，可覆盖{months:.1f}个月的经营现金流出",
        })

    # Debt-to-equity check
    ltd = get_metric_value(bs, "long_term_debt")[0]
    if ltd and total_eq:
        d_to_e = ltd / total_eq if total_eq != 0 else 0
        analysis["risk_factors"].append({
            "type": "债务 equity 比",
            "detail": f"{d_to_e:.2f}x",
            "assessment": "偏高" if d_to_e > 2 else "适中",
        })

    # Revenue growth assessment
    rev_yoy = ratios.get("revenue_yoy_change_pct")
    ni_yoy = ratios.get("net_income_yoy_change_pct")
    if rev_yoy is not None:
        assessment = "强劲增长" if rev_yoy > 15 else "稳健增长" if rev_yoy > 5 else "增长放缓" if rev_yoy > 0 else "收入下滑"
        analysis["highlights"].append({
            "type": "营收增长",
            "detail": f"营收同比{rev_yoy:+.1f}%，{assessment}",
        })
    if ni_yoy is not None:
        analysis["highlights"].append({
            "type": "利润增长",
            "detail": f"净利润同比{ni_yoy:+.1f}%",
        })

    # MD&A summary
    if mda.get("mda_text"):
        # Extract first meaningful sentence
        mda_text = mda["mda_text"]
        # Keep a condensed version
        analysis["mda_summary"] = mda_text[:2000].strip()
    if mda.get("guidance_outlook"):
        analysis["guidance_outlook"] = mda["guidance_outlook"][:1500].strip()
    if mda.get("risk_factors"):
        analysis["risk_factors_section"] = mda["risk_factors"][:1500].strip()

    return analysis


def generate_report_markdown(analysis: dict) -> str:
    """
    Generate a Markdown report from the analysis data.
    The narrative sections use data-driven observations.
    """
    ticker = analysis["ticker"]
    company = analysis.get("company_name", ticker)
    form_type = analysis["form_type"]
    filing_date = analysis["filing_date"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = []
    lines.append(f"## 📊 {company}（{ticker}）{form_type} 财报总结")
    lines.append(f"**发布日期**：{filing_date} | **财报类型**：{form_type} | **生成时间**：{now}")
    lines.append("")

    # 🔥 Hotspots
    lines.append("### 🔥 热点")
    lines.append("- 待 AI Agent 补充市场热点（数据驱动的亮点和行业关注点）")
    lines.append("")

    # ✨ Highlights
    lines.append("### ✨ 亮点")
    highlights = analysis.get("highlights", [])
    if highlights:
        for h in highlights:
            lines.append(f"- **{h['type']}**：{h['detail']}")
    else:
        lines.append("- 待补充具体亮点")
    lines.append("")

    # 👍 Strengths
    lines.append("### 👍 优点")
    strengths = analysis.get("strengths", [])
    if strengths:
        for s in strengths:
            lines.append(f"- **{s['type']}**：{s['detail']}")
    else:
        lines.append("- 待数据进一步分析")

    # Financial health indicators
    if analysis.get("cross_validation"):
        cv = analysis["cross_validation"]
        if cv.get("ocf_to_ni_ratio"):
            ocf_ratio = cv["ocf_to_ni_ratio"]
            lines.append(f"- **现金流质量**：经营活动现金流/净利润 = {ocf_ratio:.2f}x"
                        f"{'（盈利质量优秀）' if ocf_ratio >= 1 else '（需关注盈利质量）'}")
    lines.append("")

    # ⚠️ Risks
    lines.append("### ⚠️ 缺点与风险")
    risks = analysis.get("risk_factors", [])
    if risks:
        for r in risks:
            lines.append(f"- **{r['type']}**：{r['detail']}（{r.get('assessment', '')}）")

    anomalies = analysis.get("anomalies", [])
    if anomalies:
        lines.append("")
        lines.append("**⚠️ 重大波动提醒（YoY变化超过±20%）：**")
        for a in anomalies[:5]:
            lines.append(f"- {a['statement']}.{a['metric']}：{a['change_pct']:+.1f}%"
                        f"（{format_currency(a['previous'])} → {format_currency(a['current'])}）")
    lines.append("")

    # Cross-validation
    if analysis.get("cross_validation"):
        cv = analysis["cross_validation"]
        lines.append("**✅ 财务勾稽验证：**")
        lines.append(f"- {cv.get('explanation', '')}")
        if cv.get("balance_check"):
            bc = cv["balance_check"]
            lines.append(f"- 资产负债表平衡检查：{bc.get('status', '')}"
                        f"（偏差{bc.get('assets_liab_equity_diff_pct', 'N/A')}%）")
    lines.append("")

    # 📈 Key Metrics Table
    lines.append("### 📈 关键指标速览")
    lines.append("| 指标 | 本季实际 | 同比变化 |")
    lines.append("|------|---------|---------|")
    for row in analysis.get("key_metrics_table", []):
        lines.append(f"| {row['指标']} | {row['本季实际']} | {row['同比变化']} |")
    lines.append("")

    # 📝 MD&A Summary
    lines.append("### 📝 MD&A（管理层讨论与分析）摘要")
    if analysis.get("mda_summary"):
        lines.append("```")
        lines.append(analysis["mda_summary"][:1500])
        lines.append("```")
    else:
        lines.append("（MD&A文本未提取到，请参考完整财报原文）")
    lines.append("")

    # Outlook
    if analysis.get("guidance_outlook"):
        lines.append("### 🔮 管理层预期/指南")
        lines.append("```")
        lines.append(analysis["guidance_outlook"][:1000])
        lines.append("```")
        lines.append("")

    # Data Source
    lines.append("### 🔍 数据来源与引用")
    lines.append(f"- 财务数据来自 SEC EDGAR {form_type} 申报文件（XBRL结构化数据）")
    lines.append(f"- MD&A段落摘自申报文件HTML全文")
    lines.append(f"- 分析引擎：EarningsBot v1.0（现并入 Quant Copilot）")
    lines.append("")
    lines.append("---")
    lines.append(f"*报告生成时间：{now} | 数据截至：{filing_date}*")

    return "\n".join(lines)


def save_report(ticker: str, report_text: str):
    """Save the report to disk."""
    report_path = cfg.REPORT_OUTPUT_DIR / f"{ticker}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    cfg.logger.info(f"Report saved: {report_path}")
    return report_path


def run():
    """Main entry point: load processed filings, analyze, generate reports."""
    processed = load_processed_filings()
    if not processed:
        cfg.logger.info("No processed filings found to generate reports")
        return []

    cfg.logger.info(f"Generating reports for {len(processed)} filings...")

    # Load company names
    company_names = {}
    if cfg.ALL_COMPANIES_FILE.exists():
        with open(cfg.ALL_COMPANIES_FILE) as f:
            for c in json.load(f):
                company_names[c["ticker"]] = c.get("name", "")

    reports = []
    for p in processed:
        if p.get("status") != "completed":
            cfg.logger.info(f"  Skipping {p.get('ticker')} (status: {p.get('status')})")
            continue

        ticker = p.get("ticker", "")
        analysis = generate_financial_analysis(p)
        analysis["company_name"] = company_names.get(ticker, ticker)

        report_text = generate_report_markdown(analysis)
        report_path = save_report(ticker, report_text)

        reports.append({
            "ticker": ticker,
            "company_name": analysis["company_name"],
            "form_type": p.get("form_type"),
            "report_path": str(report_path),
            "report_text": report_text,
            "analysis": analysis,
        })

        cfg.logger.info(f"  ✓ {ticker} report generated: {report_path}")

    # Save summary
    summary_path = cfg.REPORT_OUTPUT_DIR / f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, indent=2, ensure_ascii=False, default=str)

    cfg.logger.info(f"Done. {len(reports)} reports generated. Summary: {summary_path}")
    return reports
