"""PDF and CSV exports. Built server-side from the server-held, validated report only."""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ATTRIBUTION = "Data: Online Retail II, UCI Machine Learning Repository. Daqing Chen. DOI 10.24432/C5CG6D. Licensed CC BY 4.0."


def metrics_csv(report: dict) -> str:
    out = io.StringIO(); w = csv.writer(out)
    w.writerow(["evidence_id", "tool", "metric", "value"])
    for ev in report["evidence"]:
        for k, v in ev["result"]["metrics"].items():
            w.writerow([ev["id"], ev["tool"], k, v])
    return out.getvalue()


def table_csv(report: dict, evidence_id: str, table: str) -> str | None:
    for ev in report["evidence"]:
        if ev["id"] == evidence_id and table in ev["result"]["tables"]:
            rows = ev["result"]["tables"][table]
            out = io.StringIO()
            if rows:
                w = csv.DictWriter(out, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
            return out.getvalue()
    return None


def tool_table_csv(result: dict, table: str) -> str | None:
    rows = result["tables"].get(table)
    if rows is None:
        return None
    out = io.StringIO()
    if rows:
        w = csv.DictWriter(out, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return out.getvalue()


def _bar(labels, values, title):
    d = Drawing(480, 170)
    c = VerticalBarChart(); c.x, c.y, c.width, c.height = 40, 40, 420, 100
    c.data = [list(values)]; c.categoryAxis.categoryNames = [str(l)[:14] for l in labels]
    c.categoryAxis.labels.angle = 40; c.categoryAxis.labels.fontSize = 5; c.categoryAxis.labels.boxAnchor = "ne"
    c.valueAxis.labels.fontSize = 6; c.bars[0].fillColor = colors.HexColor("#6d5ef5"); c.valueAxis.valueMin = 0
    d.add(c)
    from reportlab.graphics.shapes import String
    d.add(String(40, 155, title, fontSize=8, fillColor=colors.HexColor("#333333")))
    return d


def _chart(ev: dict):
    t, tabs = ev["tool"], ev["result"]["tables"]
    if t == "get_revenue_trend" and tabs.get("monthly"):
        m = tabs["monthly"]; return _bar([r["year_month"] for r in m], [r["revenue"] for r in m], "Monthly revenue (GBP)")
    if t == "get_country_performance" and tabs.get("countries"):
        m = tabs["countries"]; return _bar([r["country"] for r in m], [r["revenue"] for r in m], "Revenue by country (GBP)")
    if t == "get_product_performance" and tabs.get("top_products"):
        m = tabs["top_products"]; return _bar([r["stock_code"] for r in m], [r["revenue"] for r in m], "Top products by revenue (GBP)")
    if t == "get_cancellation_analysis" and tabs.get("monthly"):
        m = [r for r in tabs["monthly"] if r.get("cancellation_rate_pct") is not None]
        return _bar([r["year_month"] for r in m], [r["cancellation_rate_pct"] for r in m], "Cancellation invoice rate (%)") if m else None
    if t == "get_seasonality_analysis" and tabs.get("calendar_month_index"):
        m = tabs["calendar_month_index"]; return _bar([r["calendar_month"] for r in m], [r["seasonal_index"] for r in m], "Seasonal index (1.0 = average month)")
    return None


def report_pdf(report: dict, question: str) -> bytes:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=20, textColor=colors.HexColor("#14141f"), alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=colors.HexColor("#4b3fd1"), spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9, leading=12.5)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, textColor=colors.HexColor("#666666"))
    P = lambda t, s=body: Paragraph(escape(str(t)), s)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="OpsLens Investigation Report", author="OpsLens")
    s = [P("OpsLens Investigation Report", h1), P(question, small)]
    gen = report.get("generated_by")
    s.append(P("AI-interpreted report. Every figure was checked against executed tool outputs." if gen == "ai"
               else "Deterministic report: figures are direct outputs of analytical tools; no AI interpretation was applied.", small))
    s += [P("Executive summary", h2), P(report["executive_summary"]), P("Investigation objective", h2), P(report.get("objective", ""))]
    s.append(P("Tools executed", h2))
    rows = [["ID", "Tool", "Arguments"]] + [[t["id"], t["tool"], str(t["args"] or "defaults")[:70]] for t in report["tools_executed"]]
    tb = Table(rows, colWidths=[14 * mm, 62 * mm, 98 * mm]); tb.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececf8")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#bbbbcc"))]))
    s.append(tb)
    s.append(P("Key findings", h2))
    for f in report["findings"]:
        s += [P(f"{f['title']}  [{', '.join(f['evidence_ids'])}]", ParagraphStyle("fh", parent=body, fontName="Helvetica-Bold")), P(f["text"]), Spacer(1, 3)]
    if report.get("anomalies"):
        s.append(P("Anomalies", h2)); s += [P("- " + a) for a in report["anomalies"]]
    s.append(P("Supporting metrics and charts", h2))
    for ev in report["evidence"]:
        s.append(P(f"{ev['id']}  {ev['tool']}", ParagraphStyle("eh", parent=body, fontName="Helvetica-Bold")))
        ms = [[k.replace("_", " "), "" if v is None else str(v)] for k, v in list(ev["result"]["metrics"].items())[:14]]
        if ms:
            t = Table(ms, colWidths=[70 * mm, 60 * mm]); t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ccccdd"))])); s.append(t)
        ch = _chart(ev)
        if ch: s.append(ch)
        s.append(Spacer(1, 5))
    if report.get("implications"):
        s.append(P("Business implications", h2)); s += [P("- " + a) for a in report["implications"]]
    if report.get("actions"):
        s.append(P("Recommended actions", h2)); s += [P("- " + a) for a in report["actions"]]
    c = report["confidence"]
    s += [P("Confidence", h2), P(f"{c['level'].title()}: {c['rationale']}"), P("Data limitations", h2)] + [P("- " + l) for l in report["limitations"]]
    s += [Spacer(1, 8), P(ATTRIBUTION, small)]
    doc.build(s)
    return buf.getvalue()
