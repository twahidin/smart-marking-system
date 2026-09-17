"""Render one assignment's insights as a PDF the teacher can print or file: the numbers (how far the
class got, mean % per part as a bar chart, the allocations lost most often) and, when the narrative
has been generated, the summary, strengths, gaps, recommendations and who to follow up.

Statistics alone are enough to render: with no report the narrative sections are replaced by a note."""
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

CHART_W = 16 * cm
CHART_H = 6 * cm
MAX_BARS = 20          # beyond this the labels stop being readable, so the chart shows the weakest parts
STRAIGHT_LABELS = 8    # up to this many bars the part labels sit straight under them
NO_REPORT = "AI narrative not generated yet — the numbers below are live."
HEADER_FILL = colors.HexColor("#D9E2F3")
BAR_FILL = colors.HexColor("#4472C4")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=base["BodyText"], fontSize=9.5, leading=13, alignment=TA_LEFT,
                          spaceAfter=4)
    return {
        "title": ParagraphStyle("TitleX", parent=base["Title"], fontSize=17, leading=21, spaceAfter=2),
        "sub": ParagraphStyle("Sub", parent=body, fontSize=9, textColor=colors.HexColor("#555555"), spaceAfter=10),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=12, leading=15, spaceBefore=12, spaceAfter=4),
        "body": body,
        "bold": ParagraphStyle("Bold", parent=body, fontName="Helvetica-Bold"),
        "note": ParagraphStyle("Note", parent=body, textColor=colors.HexColor("#8A6D00")),
        "cell": ParagraphStyle("Cell", parent=body, fontSize=9, leading=12, spaceAfter=0),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "")), style)


def _bullets(items: List[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable([ListItem(_p(i, style), leftIndent=12) for i in items],
                        bulletType="bullet", start="•", leftIndent=12)


def _headline(stats: Dict[str, Any]) -> str:
    """"12 of 30 marked, 3 waiting — mean 14.5 / 20"."""
    n_marked, n_students = int(stats.get("n_marked") or 0), int(stats.get("n_students") or 0)
    totals = stats.get("totals") or {}
    bits = [f"{n_marked} of {n_students} marked"]
    if stats.get("n_pending"):
        bits.append(f"{stats['n_pending']} still being marked or waiting for you")
    if totals.get("mean") is not None:
        bits.append(f"mean {totals['mean']} / {totals.get('max', 0)}")
    return ", ".join(bits)


def _chart(parts: List[dict]) -> Optional[Drawing]:
    """Mean % per part, weakest parts first when there are too many to fit."""
    scored = [p for p in parts if p.get("mean_pct") is not None]
    if not scored:
        return None
    if len(scored) > MAX_BARS:
        scored = sorted(scored, key=lambda p: p["mean_pct"])[:MAX_BARS]
    drawing = Drawing(CHART_W, CHART_H)
    chart = VerticalBarChart()
    chart.x, chart.y = 1.6 * cm, 1.4 * cm
    chart.width, chart.height = CHART_W - 2.2 * cm, CHART_H - 2.0 * cm
    chart.data = [[float(p["mean_pct"]) for p in scored]]
    chart.bars[0].fillColor = BAR_FILL
    chart.barSpacing = 2
    chart.groupSpacing = 8
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 25
    chart.valueAxis.labelTextFormat = "%d%%"
    chart.categoryAxis.categoryNames = [str(p.get("label") or p.get("q_id") or "") for p in scored]
    # Part labels sit under their bar while they still fit; past that they lean to stay readable.
    tilted = len(scored) > STRAIGHT_LABELS
    chart.categoryAxis.labels.boxAnchor = "ne" if tilted else "n"
    chart.categoryAxis.labels.angle = 30 if tilted else 0
    chart.categoryAxis.labels.dx, chart.categoryAxis.labels.dy = (-2, -2) if tilted else (0, -3)
    chart.categoryAxis.labels.fontSize = 7.5
    drawing.add(chart)
    return drawing


def _parts_table(parts: List[dict], st: Dict[str, ParagraphStyle]) -> Table:
    head = ["Part", "Max", "Marked", "Mean %", "Full marks", "Zero"]
    rows = [[_p(h, st["cell"]) for h in head]]
    for p in parts:
        mean = "—" if p.get("mean_pct") is None else f"{p['mean_pct']}%"
        rows.append([_p(p.get("label") or p.get("q_id"), st["cell"]), _p(p.get("max"), st["cell"]),
                     _p(p.get("attempted"), st["cell"]), _p(mean, st["cell"]),
                     _p(p.get("full"), st["cell"]), _p(p.get("zero"), st["cell"])])
    table = Table(rows, colWidths=[6 * cm, 1.8 * cm, 2.2 * cm, 2.2 * cm, 2.4 * cm, 1.8 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _support_table(support: List[dict], names: Dict[int, str], st: Dict[str, ParagraphStyle]) -> Table:
    rows = [[_p("Students", st["cell"]), _p("Focus", st["cell"])]]
    for s in support:
        who = ", ".join(f"#{n} {names[n]}" if n in names else f"#{n}" for n in (s.get("reg_nos") or []))
        rows.append([_p(who, st["cell"]), _p(s.get("focus"), st["cell"])])
    table = Table(rows, colWidths=[7 * cm, 9.4 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _labels(stats: Dict[str, Any]) -> Dict[str, str]:
    """part id -> the label the tables and the chart use ("9b" -> "9(b)"), so the narrative names a
    part the same way the numbers above it do."""
    return {p["q_id"]: p.get("label") or p["q_id"] for p in (stats.get("parts") or [])}


def _named(part_ids: Any, labels: Dict[str, str]) -> str:
    ids = list(part_ids or [])
    return ", ".join(labels.get(q, q) for q in ids) or "—"


def _numbers(stats: Dict[str, Any], st: Dict[str, ParagraphStyle]) -> List[Any]:
    """Marks by part (chart then table) and the allocations the class lost most often."""
    out: List[Any] = []
    parts = stats.get("parts") or []
    if parts:
        out.append(Paragraph("Marks by part", st["h2"]))
        chart = _chart(parts)
        if chart is not None:
            out.extend([chart, Spacer(1, 4)])
        out.append(_parts_table(parts, st))
    most_lost = stats.get("most_lost") or []
    if most_lost:
        labels = _labels(stats)
        out.append(Paragraph("Most-lost allocations", st["h2"]))
        out.append(_bullets([f"{labels.get(a['q_id'], a['q_id'])} — {a['label']}: lost by {a['lost']} of "
                             f"{a['of']} marked" for a in most_lost], st["body"]))
    return out


def _narrative(report: Dict[str, Any], names: Dict[int, str], labels: Dict[str, str],
               st: Dict[str, ParagraphStyle]) -> List[Any]:
    out: List[Any] = []
    if report.get("strengths"):
        out.append(Paragraph("Strengths", st["h2"]))
        out.append(_bullets(list(report["strengths"]), st["body"]))
    if report.get("gaps"):
        out.append(Paragraph("Gaps", st["h2"]))
        for g in report["gaps"]:
            parts = _named(g.get("part_ids"), labels)
            out.append(KeepTogether([
                _p(f"{g.get('title')} ({parts})", st["bold"]),
                _p(f"{g.get('what_went_wrong')} — {g.get('students_affected', 0)} script(s) affected", st["body"]),
                Spacer(1, 2)]))
    if report.get("recommendations"):
        out.append(Paragraph("Recommendations", st["h2"]))
        out.append(_bullets([f"{r.get('title')} ({_named(r.get('part_ids'), labels)}): {r.get('detail')}"
                             for r in report["recommendations"]], st["body"]))
    if report.get("students_to_support"):
        out.append(Paragraph("Students to support", st["h2"]))
        out.append(_support_table(report["students_to_support"], names, st))
    return out


def render_insights_pdf(ca: dict, stats: Dict[str, Any], report: Optional[Dict[str, Any]],
                        students_by_reg: Dict[int, str]) -> bytes:
    """The insights PDF for one assignment. `students_by_reg` puts the names back on the register
    numbers the narrative uses — the model never saw them."""
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm,
                            title=f"{ca.get('title') or 'Assignment'} — insights", author="Smart Marking System")
    generated = datetime.now(timezone.utc).strftime("%d %b %Y")
    subtitle = " · ".join(x for x in [ca.get("class_name"), generated, _headline(stats)] if x)
    story: List[Any] = [_p(ca.get("title") or "Assignment", st["title"]), _p(subtitle, st["sub"])]
    if report:
        story.append(Paragraph("Summary", st["h2"]))
        story.append(_p(report.get("summary") or "", st["body"]))
    else:
        story.append(Paragraph(escape(NO_REPORT), st["note"]))
    story.extend(_numbers(stats, st))
    if report:
        story.extend(_narrative(report, students_by_reg, _labels(stats), st))
    doc.build(story)
    return buf.getvalue()
