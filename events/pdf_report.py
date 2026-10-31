"""Generate a real PDF shift report (not the browser's print dialog) from the same numbers the
Shift Report tab shows: insights.analyse(), shift_summary.summarize() and root_cause.analyse().
No new numbers are computed here -- this is a rendering layer over already-measured data.

Usage: python events/pdf_report.py <clip_id> [<clip_id> ...] > shift_report.pdf
"""
import datetime
import io
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer,
                                 Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights  # noqa: E402
import root_cause  # noqa: E402
import shift_summary  # noqa: E402

ACCENT = colors.HexColor("#1d3350")
MUTED = colors.HexColor("#6e7b88")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Head", parent=ss["Heading1"], fontSize=18, spaceAfter=4))
    ss.add(ParagraphStyle("Sub", parent=ss["Normal"], textColor=MUTED, spaceAfter=14))
    ss.add(ParagraphStyle("Sec", parent=ss["Heading2"], fontSize=12, spaceBefore=14, spaceAfter=6))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=10, leading=14))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8, textColor=MUTED, leading=11))
    return ss


def build(clip_ids, shift_hours=8.0, out=None):
    """Returns PDF bytes (writes to `out`, a file-like object, if given)."""
    report = insights.analyse(clip_ids, shift_hours)
    summary = shift_summary.summarize(clip_ids, shift_hours)
    causes = root_cause.analyse(clip_ids)
    ss = _styles()
    buf = out or io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=16 * mm,
                             leftMargin=18 * mm, rightMargin=18 * mm)
    date = datetime.date.today().strftime("%d %b %Y")
    story = [
        Paragraph("Kairo -- Shift Summary", ss["Head"]),
        Paragraph(f"{date} &middot; {len(clip_ids)} clips &middot; {report['observed_min']} min observed "
                  f"&middot; extrapolated to {shift_hours:g}h shift", ss["Sub"]),
        Paragraph(summary["narrative"], ss["Body"]),
        Spacer(1, 10),
    ]

    tiles = [
        ["Work steps", str(report["steps"])],
        ["Hands-on work", f"{report['breakdown_pct'].get('work', 0)}%"],
        ["Search time", f"{report['breakdown_pct'].get('search', 0)}%"],
        ["Recoverable value", f"EUR {report['roi_eur_per_year_total']:,} / year"],
        ["Est. lost time", f"{report['lost_min_per_shift']} min / shift"],
    ]
    t = Table(tiles, colWidths=[90 * mm, 70 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [t]

    if report["recommendations"]:
        story.append(Paragraph("Top recommendations", ss["Sec"]))
        items = [ListItem(Paragraph(
            f"<b>{r['title']}</b>: saves ~{r['saving_min_per_shift']} min/shift "
            f"(EUR {r['roi_eur_per_year']:,}/yr, {round(100 * r['confidence'])}% confidence). {r['support']}.",
            ss["Body"])) for r in report["recommendations"][:4]]
        story.append(ListFlowable(items, bulletType="bullet"))

    if causes:
        story.append(Paragraph("Root cause findings", ss["Sec"]))
        items = [ListItem(Paragraph(
            f"<b>{f['step_label']}</b> ({f['clip_id']}): {f['root_cause']} Fix: {f['fix']}", ss["Body"]))
            for f in causes[:4]]
        story.append(ListFlowable(items, bulletType="bullet"))

    story.append(Paragraph("Friction detail", ss["Sec"]))
    rows = [["Type", "Events", "Seconds"]] + [
        [k, str(v["count"]), str(v["seconds"])] for k, v in report["friction"].items() if v["count"]]
    ft = Table(rows, colWidths=[70 * mm, 40 * mm, 40 * mm])
    ft.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ft)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Kairo evaluates the process and the workstation, not individual workers. "
        + report["assumptions"]["note"], ss["Small"]))

    doc.build(story)
    if out is None:
        return buf.getvalue()
    return None


if __name__ == "__main__":
    sys.stdout.buffer.write(build(sys.argv[1:]))
