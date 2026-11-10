"""PDF report builder (reportlab) — plain tables, no external assets."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.ml.history_stats import STATS_REGIMES


def build_pdf_report(ctx: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15 * mm, bottomMargin=15 * mm)
    story: list = []

    def h(text, size=13):
        from reportlab.lib.styles import ParagraphStyle

        style = ParagraphStyle(name="h", fontName="Helvetica-Bold", fontSize=size, spaceAfter=6)
        story.append(Paragraph(text, style))

    def p(text):
        from reportlab.lib.styles import ParagraphStyle

        style = ParagraphStyle(name="p", fontName="Helvetica", fontSize=9, leading=12)
        story.append(Paragraph(text, style))

    def table(headers, rows, widths=None):
        data = [headers] + rows
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(t)
        story.append(Spacer(1, 5 * mm))

    run = ctx["run"]
    h("GMRAI — Historical Market Regime Report")
    p(
        f"Symbol XAUUSD · Timeframe M15 · Source {run['data_source']} · "
        f"Data {run['data_start']} → {run['data_end']} · Bars {run['bars']} · "
        f"Segments {run['segments']} · HMM v{run['hmm_version']} · RF v{run['rf_version']}"
    )
    p("GMRAI là công cụ nghiên cứu. Kết quả phân tích không phải lời khuyên đầu tư và không gửi lệnh giao dịch.")
    story.append(Spacer(1, 4 * mm))

    h("1. Regime duration statistics")
    rows = []
    for r in STATS_REGIMES:
        d = ctx["duration"][r]
        rows.append(
            [r, d["occurrences"], d["total_minutes"], f"{d['occupancy_pct']}%",
             d["mean_minutes"] or "—", d["median_minutes"] or "—",
             d["longest_minutes"] or "—", d["shortest_minutes"] or "—",
             d["p90"] or "—"]
        )
    table(
        ["Regime", "Occurrences", "Total (min)", "Occupancy", "Mean", "Median", "Longest", "Shortest", "p90"],
        rows,
    )

    h("2. Trend analysis")
    rows = []
    for r in ("TREND_UP", "TREND_DOWN"):
        t = ctx["trends"].get(r, {})
        if t.get("count"):
            rows.append([r, t["count"], t["total_minutes"], t["mean_minutes"], t["longest_minutes"],
                         t["mean_speed_usd_per_min"], t["mean_atr_ratio"], t["mean_adx_norm"],
                         t["mean_efficiency"]])
    table(["Direction", "Count", "Total (min)", "Mean", "Longest", "Speed $/min", "ATR", "ADX", "Eff."], rows)

    h("3. Sideways analysis")
    s = ctx["sideways"]
    if s.get("count"):
        table(
            ["Metric", "Value"],
            [
                ["Count / total minutes", f"{s['count']} / {s['total_minutes']}"],
                ["Mean / longest (min)", f"{s['mean_minutes']} / {s['longest_minutes']}"],
                ["Mean range width", s["mean_range_width"]],
                ["Mean touches high / low", f"{s['mean_touches_high']} / {s['mean_touches_low']}"],
                ["Breakouts / false breakouts", f"{s['breakouts']} / {s['false_breakouts']}"],
            ],
        )
    h("Sideways duration buckets")
    table(["Bucket", "Count"], [[k, v] for k, v in s.get("buckets", {}).items()])

    h("4. Early Trend analysis")
    rows = []
    for d in ("EARLY_TREND_UP", "EARLY_TREND_DOWN"):
        e = ctx["early_trend"].get(d, {})
        rows.append([d, e.get("signals", 0), e.get("confirmed", 0), f"{e.get('success_rate_pct')}%",
                     e.get("false_rate_pct"), e.get("mean_detection_delay_bars") or "—"])
    table(["Signal", "Total", "Confirmed", "Success", "False %", "Delay (bars)"], rows)

    h("5. Transition matrix (rates)")
    tm = ctx["transitions"]
    regs = tm["regimes"]
    rows = []
    for a in regs:
        rows.append([a] + [tm["rates"][a].get(b, 0) for b in regs])
    table(["From \\ To"] + regs, rows)

    h("6. Segment list (top 200)")
    rows = []
    for seg in ctx["segments"][:200]:
        rows.append([seg["segment_index"], seg["regime"], seg["start_ts"][:16], seg["end_ts"][:16],
                     seg["duration_minutes"], seg["start_price"], seg["end_price"], seg["net_change"]])
    table(["#", "Regime", "Start (UTC)", "End (UTC)", "Min", "Start px", "End px", "Net"], rows)

    doc.build(story)
    return buf.getvalue()
