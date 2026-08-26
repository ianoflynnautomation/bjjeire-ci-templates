from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import ExecutiveReport

NAVY = colors.HexColor("#0f172a")
EMERALD = colors.HexColor("#047857")
RED = colors.HexColor("#b91c1c")
AMBER = colors.HexColor("#b45309")
SLATE = colors.HexColor("#334155")
LINE = colors.HexColor("#cbd5e1")
ROW_ALT = colors.HexColor("#f8fafc")
WHITE = colors.white
VERDICT_FILL = {"PASS": EMERALD, "FAIL": RED}


def write_pdf(report: ExecutiveReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    page = landscape(A4)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=page,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{report.meta.release_id} {report.meta.title}",
        author=report.meta.actor,
        subject="SOC 2 / ISO 27001 evidence pack — test execution",
    )
    story = [
        _header(report, styles),
        Spacer(1, 6),
        Paragraph("1. Release identification & execution environment", styles["h2"]),
        _meta_table(report, styles),
        Spacer(1, 8),
        Paragraph("2. Test results breakdown matrix", styles["h2"]),
        _matrix(report, styles),
        Spacer(1, 8),
        Paragraph("3. Artifact catalog & provenance", styles["h2"]),
        _catalog(report, styles),
        Spacer(1, 8),
        Paragraph("4. Failure / exception log", styles["h2"]),
        _failures_table(report, styles),
        Spacer(1, 8),
        *_optional_performance(report, styles),
        Paragraph("5. Attestation notes", styles["h2"]),
        *_notes(report, styles),
    ]
    doc.build(story, onFirstPage=_page_footer(report), onLaterPages=_page_footer(report))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=NAVY, spaceBefore=2, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica", fontSize=8, textColor=SLATE, leading=11),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontName="Helvetica", fontSize=7, textColor=NAVY, leading=9),
        "cellBold": ParagraphStyle("cellBold", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7, textColor=WHITE, leading=9),
        "muted": ParagraphStyle("muted", parent=base["BodyText"], fontName="Helvetica", fontSize=7, textColor=SLATE, alignment=TA_RIGHT),
        "verdict": ParagraphStyle("verdict", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=12, textColor=WHITE, alignment=TA_LEFT),
    }


def _header(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> Table:
    left = [
        Paragraph(report.meta.title, styles["h1"]),
        Paragraph(
            f"Release ID <b>{_esc(report.meta.release_id)}</b> &nbsp;|&nbsp; {_esc(report.meta.product)} "
            f"&nbsp;|&nbsp; generated { _esc(report.meta.generated_at)}",
            styles["body"],
        ),
    ]
    chip = Table([[Paragraph(report.verdict, styles["verdict"])]], colWidths=[32 * mm])
    chip.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), VERDICT_FILL[report.verdict]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    header = Table([[left, chip]], colWidths=[220 * mm, 36 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    return header


def _meta_table(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> Table:
    meta = report.meta
    rows = [
        [_h("Field", styles), _h("Value", styles), _h("Field", styles), _h("Value", styles)],
        [_c("Release ID", styles), _c(meta.release_id, styles), _c("Git SHA", styles), _c(meta.git_sha[:12], styles)],
        [_c("Branch", styles), _c(meta.branch, styles), _c("Git ref", styles), _c(meta.git_ref, styles)],
        [_c("Target environment", styles), _c(meta.environment, styles), _c("Pipeline run ID", styles), _c(meta.pipeline_run_id, styles)],
        [_c("CI runner host", styles), _c(meta.runner_host, styles), _c("Triggered by", styles), _c(meta.actor, styles)],
        [_c("Timestamp (UTC)", styles), _c(meta.generated_at, styles), _c("Workflow", styles), _c(meta.workflow, styles)],
    ]
    table = Table(rows, colWidths=[40 * mm, 88 * mm, 40 * mm, 88 * mm])
    table.setStyle(_grid())
    return table


def _matrix(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> Table:
    header = [
        _h("Stage / Test type", styles),
        _h("Environment", styles),
        _h("Total", styles),
        _h("Passed", styles),
        _h("Failed", styles),
        _h("Skipped", styles),
        _h("Pass rate (%)", styles),
        _h("Duration (s)", styles),
        _h("Compliance gate", styles),
    ]
    rows = [header]
    for category in report.required:
        rate = f"{category.pass_rate:.1f}" if category.pass_rate is not None else "—"
        rows.append(
            [
                _c(category.title, styles),
                _c(category.environment or report.meta.environment, styles),
                _c(str(category.tests), styles),
                _c(str(category.passed), styles),
                _c(str(category.failed + category.errors), styles),
                _c(str(category.skipped), styles),
                _c(rate, styles),
                _c(f"{category.duration_s:.1f}", styles),
                _c(category.gate_status, styles),
            ]
        )
    totals_rate = f"{report.pass_rate:.1f}" if report.pass_rate is not None else "—"
    rows.append(
        [
            _c("<b>Release total</b>", styles),
            _c(report.meta.environment, styles),
            _c(str(report.tests), styles),
            _c(str(report.passed), styles),
            _c(str(report.failed), styles),
            _c(str(report.skipped), styles),
            _c(totals_rate, styles),
            _c(f"{report.duration_s:.1f}", styles),
            _c(report.verdict, styles),
        ]
    )
    table = Table(rows, colWidths=[42 * mm, 28 * mm, 18 * mm, 20 * mm, 18 * mm, 20 * mm, 26 * mm, 26 * mm, 48 * mm], repeatRows=1)
    table.setStyle(_grid())
    return table


def _catalog(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> Table | Paragraph:
    if not report.catalog:
        return Paragraph("No input artifacts were present. All required gates are <b>MISSING / CRITICAL FAILURE</b>.", styles["body"])
    rows = [
        [
            _h("Artifact name", styles),
            _h("Type", styles),
            _h("Source job / stage", styles),
            _h("Storage path", styles),
            _h("SHA-256", styles),
        ]
    ]
    for record in report.catalog:
        rows.append(
            [
                _c(record.name, styles),
                _c(record.artifact_type, styles),
                _c(record.source_job, styles),
                _c(_esc(record.storage_path), styles),
                _c(f"<font face='Courier' size='6'>{record.sha256}</font>", styles),
            ]
        )
    table = Table(rows, colWidths=[38 * mm, 32 * mm, 32 * mm, 70 * mm, 84 * mm], repeatRows=1)
    table.setStyle(_grid())
    return table


def _failures_table(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> Table | Paragraph:
    rows = [[_h("Stage", styles), _h("Case", styles), _h("Detail", styles)]]
    count = 0
    for category in report.categories:
        for case in category.failures[:20]:
            count += 1
            rows.append(
                [
                    _c(category.title, styles),
                    _c(f"{_esc(case.classname)}<br/>{_esc(case.name)}", styles),
                    _c(_esc((case.message or case.status)[:240]), styles),
                ]
            )
    if count == 0:
        return Paragraph("No failing test cases in parsed artifacts.", styles["body"])
    table = Table(rows, colWidths=[40 * mm, 80 * mm, 136 * mm], repeatRows=1)
    table.setStyle(_grid())
    return table


def _optional_performance(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> list:
    perf = next((c for c in report.categories if c.id == "performance" and c.metrics), None)
    if perf is None or perf.metrics is None:
        return []
    metrics = perf.metrics
    rows = [
        [_h("Metric", styles), _h("Value", styles)],
        [_c("p95 latency (ms)", styles), _c(_num(metrics.p95_ms), styles)],
        [_c("Requests / second", styles), _c(_num(metrics.rps), styles)],
        [_c("Error rate", styles), _c(_pct(metrics.error_rate), styles)],
        [_c("Lighthouse performance", styles), _c("—" if metrics.lighthouse_performance is None else f"{metrics.lighthouse_performance:.0f}/100", styles)],
        [_c("Source", styles), _c(metrics.source, styles)],
    ]
    table = Table(rows, colWidths=[60 * mm, 80 * mm])
    table.setStyle(_grid())
    return [Paragraph("Performance (optional evidence)", styles["h2"]), KeepTogether([table]), Spacer(1, 8)]


def _notes(report: ExecutiveReport, styles: dict[str, ParagraphStyle]) -> list:
    items = [
        Paragraph(
            "This pack is generated by an automated CI collector. Missing required stages are treated as "
            "<b>MISSING / CRITICAL FAILURE</b> and fail the release gate. SHA-256 values are computed over the "
            "bytes of each parsed result file at report time.",
            styles["body"],
        )
    ]
    for category in report.categories:
        for note in category.notes:
            items.append(Paragraph(f"<b>{_esc(category.title)}:</b> {_esc(note)}", styles["body"]))
    if report.meta.run_url:
        items.append(Paragraph(f"Pipeline run: {_esc(report.meta.run_url)}", styles["body"]))
    return items


def _grid() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ROW_ALT]),
        ]
    )


def _page_footer(report: ExecutiveReport):
    def _draw(canvas, doc) -> None:  # noqa: ANN001
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(doc.leftMargin, 10 * mm, landscape(A4)[0] - doc.rightMargin, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(SLATE)
        canvas.drawString(doc.leftMargin, 6 * mm, f"{report.meta.release_id}  |  {report.meta.product}  |  audit evidence")
        canvas.drawRightString(landscape(A4)[0] - doc.rightMargin, 6 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return _draw


def _h(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(text, styles["cellBold"])


def _c(text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(text, styles["cell"])


def _esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    rate = value * 100 if value <= 1 else value
    return f"{rate:.2f}%"
