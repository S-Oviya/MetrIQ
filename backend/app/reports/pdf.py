"""High-fidelity PDF generation for MetrIQ P6 reports using ReportLab.

Renders authoritative, type-specific PDFs matching the exact structure,
data fields, and design of the MetrIQ report templates.
"""
from __future__ import annotations

import io
from html import escape
from typing import Any, Dict, Iterable, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .templates import (
    TEMPLATE_VERSION,
    TITLES,
    _evidence as _html_evidence,
    _gatc as _html_gatc,
    _generic as _html_generic,
    _instrument as _template_instrument,
    _oiml as _html_oiml,
    _records as _template_records,
    _references as _template_references,
    _rejection as _html_rejection,
    _review as _template_review,
)

SUBTITLES: Dict[str, str] = {
    "OIML_R76_2_TYPE_EVALUATION": "Practice/demo type-evaluation template only; it is not an official issued OIML certificate.",
    "GATC_THIRD_SCHEDULE_VERIFICATION": "Practice/demo verification template based only on supplied P2/P3 and adapter data; it is not an official issued statutory certificate.",
    "GENERIC_VERIFICATION": "Configurable verification structure; not represented as one specific state's statutory form.",
    "REJECTION_DOCUMENT": "Backend-recorded notice layout; no measured failure is asserted beyond supplied data.",
    "TECHNICAL_EVIDENCE_ANNEX": "Supporting evidence attachment/index; it is not a certificate.",
}

# Color palette aligned with MetrIQ design system
COLOR_NAVY = colors.HexColor("#174D70")
COLOR_NAVY_DARK = colors.HexColor("#0D334A")
COLOR_TEXT = colors.HexColor("#182B3C")
COLOR_MUTED = colors.HexColor("#486581")
COLOR_BORDER = colors.HexColor("#C9D5DF")
COLOR_TH_BG = colors.HexColor("#EFF5F8")
COLOR_REJECTION = colors.HexColor("#8B1E1E")
COLOR_REJECTION_BG = colors.HexColor("#FDE8E8")
COLOR_DEMO_BG = colors.HexColor("#FFF3CD")
COLOR_DEMO_TEXT = colors.HexColor("#765300")
COLOR_DEMO_BORDER = colors.HexColor("#9A6700")
COLOR_PASS = colors.HexColor("#0E6251")
COLOR_FAIL = colors.HexColor("#8B1E1E")

USABLE_WIDTH = 523.27  # A4 width (595.27) - 2 * 36 margin


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas that renders running headers and accurate total page counts."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()

        # Running header on pages after the first
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(COLOR_NAVY)
            self.drawString(36, 816, "METRIQ")
            self.setFont("Helvetica", 7.5)
            self.setFillColor(COLOR_MUTED)
            self.drawString(74, 816, "·  NAWI TEST & VERIFICATION REPORT")
            self.setStrokeColor(COLOR_BORDER)
            self.setLineWidth(0.5)
            self.line(36, 810, 595.27 - 36, 810)

        # Running footer on every page
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(36, 32, 595.27 - 36, 32)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(COLOR_MUTED)
        self.drawString(36, 21, "CONFIDENTIAL & CONTROLLED METROLOGICAL DOCUMENT  ·  METRIQ SYSTEM")
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(595.27 - 36, 21, page_text)

        self.restoreState()


def _clean(val: Any) -> str:
    """Format and escape any value for safe ReportLab Paragraph XML."""
    if val is None or val == "":
        return "Not supplied"
    if isinstance(val, dict):
        return "Structured data supplied"
    if isinstance(val, (list, tuple, set)):
        items = [_clean(item) for item in val if item is not None and item != ""]
        return ", ".join(items) if items else "Not supplied"
    return escape(str(val))


def _make_styles() -> Dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    custom: Dict[str, ParagraphStyle] = {}

    custom["Brand"] = ParagraphStyle(
        "Brand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=COLOR_MUTED,
        textTransform="uppercase",
        spaceAfter=3,
    )
    custom["Title"] = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        textColor=COLOR_NAVY,
        spaceAfter=3,
    )
    custom["Subtitle"] = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=COLOR_MUTED,
        spaceAfter=6,
    )
    custom["MetaRight"] = ParagraphStyle(
        "MetaRight",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        alignment=2,  # Right align
        textColor=COLOR_NAVY_DARK,
    )
    custom["MetaRightSmall"] = ParagraphStyle(
        "MetaRightSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        alignment=2,
        textColor=COLOR_MUTED,
    )
    custom["SectionHeading"] = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=COLOR_NAVY,
        spaceBefore=8,
        spaceAfter=4,
    )
    custom["RejectionSectionHeading"] = ParagraphStyle(
        "RejectionSectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=COLOR_REJECTION,
        spaceBefore=8,
        spaceAfter=4,
    )
    custom["TableCell"] = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_TEXT,
    )
    custom["TableLabel"] = ParagraphStyle(
        "TableLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_NAVY_DARK,
    )
    custom["RejectionTableLabel"] = ParagraphStyle(
        "RejectionTableLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_REJECTION,
    )
    custom["TableHeader"] = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_NAVY_DARK,
    )
    custom["PassCell"] = ParagraphStyle(
        "PassCell",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_PASS,
    )
    custom["FailCell"] = ParagraphStyle(
        "FailCell",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=COLOR_FAIL,
    )
    custom["Badge"] = ParagraphStyle(
        "Badge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        alignment=1,  # Center
    )
    custom["NoticeBody"] = ParagraphStyle(
        "NoticeBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_REJECTION,
    )
    custom["NoticeTitle"] = ParagraphStyle(
        "NoticeTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=COLOR_REJECTION,
        spaceAfter=2,
    )
    custom["SignatureText"] = ParagraphStyle(
        "SignatureText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=14,
        textColor=COLOR_TEXT,
    )

    return custom


def _build_header(
    report: Dict[str, Any],
    title: str,
    subtitle: str,
    demo: bool,
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    """Construct top header matching the web template."""
    left_meta = [
        Paragraph("METRIQ · NAWI TEST &amp; VERIFICATION MANAGEMENT", styles["Brand"]),
        Paragraph(_clean(title), styles["Title"]),
        Paragraph(_clean(subtitle), styles["Subtitle"]),
    ]

    report_num = str(report.get("report_number") or report.get("report_id") or "")
    gen_at = str(report.get("generated_at") or report.get("created_at") or "")

    right_meta = [
        Paragraph(_clean(report_num), styles["MetaRight"]),
        Paragraph(f"Generated: {_clean(gen_at)}", styles["MetaRightSmall"]),
    ]

    # Two column header table
    header_table = Table(
        [[left_meta, right_meta]],
        colWidths=[USABLE_WIDTH * 0.65, USABLE_WIDTH * 0.35],
    )
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )

    # Status badge below header
    if demo:
        badge_text = "DEMO/MOCK DATA PRESENT — NOT A MEASUREMENT RECORD"
        badge_p = Paragraph(f"<b>{badge_text}</b>", ParagraphStyle(
            "DemoBadgeP",
            parent=styles["Badge"],
            textColor=COLOR_DEMO_TEXT,
        ))
        badge_tbl = Table([[badge_p]], colWidths=[USABLE_WIDTH])
        badge_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_DEMO_BG),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_DEMO_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
    else:
        badge_text = "BACKEND-RECORDED REPORT SNAPSHOT"
        badge_p = Paragraph(f"<b>{badge_text}</b>", ParagraphStyle(
            "SnapshotBadgeP",
            parent=styles["Badge"],
            textColor=COLOR_NAVY_DARK,
        ))
        badge_tbl = Table([[badge_p]], colWidths=[USABLE_WIDTH])
        badge_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_TH_BG),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))

    return [
        header_table,
        HRFlowable(width="100%", thickness=2.5, color=COLOR_NAVY, spaceBefore=2, spaceAfter=6),
        badge_tbl,
        Spacer(1, 8),
    ]


def _build_rejection_notice(results: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    outcome = _clean(results.get("outcome"))
    notice_title = Paragraph("REJECTION / NON-COMPLIANCE NOTICE", styles["NoticeTitle"])
    notice_text = Paragraph(
        f"Recorded workflow outcome: <b>{outcome}</b>. "
        "This notice presents only the information supplied to P6; it does not "
        "assert an unrecorded measured failure.",
        styles["NoticeBody"],
    )
    notice_tbl = Table([[ [notice_title, notice_text] ]], colWidths=[USABLE_WIDTH])
    notice_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_REJECTION_BG),
        ("BOX", (0, 0), (-1, -1), 1.5, COLOR_REJECTION),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return [notice_tbl, Spacer(1, 8)]


def _build_key_value_table(
    rows: Iterable[Tuple[str, Any]],
    styles: Dict[str, ParagraphStyle],
    is_rejection: bool = False,
) -> Table:
    """Render key-value table matching 32% / 68% web layout."""
    data: List[List[Any]] = []
    label_style = styles["RejectionTableLabel"] if is_rejection else styles["TableLabel"]
    val_style = styles["TableCell"]

    for k, v in rows:
        data.append([
            Paragraph(_clean(k), label_style),
            Paragraph(_clean(v), val_style),
        ])

    table = Table(data, colWidths=[USABLE_WIDTH * 0.32, USABLE_WIDTH * 0.68])
    bg_color = COLOR_REJECTION_BG if is_rejection else COLOR_TH_BG

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), bg_color),
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_observations_table(
    items: Any,
    styles: Dict[str, ParagraphStyle],
    is_rejection: bool = False,
) -> Any:
    rows = items if isinstance(items, list) else []
    if not rows:
        return Paragraph("No observations supplied.", styles["TableCell"])

    headers = [
        Paragraph("<b>Observation</b>", styles["TableHeader"]),
        Paragraph("<b>Description</b>", styles["TableHeader"]),
        Paragraph("<b>Result</b>", styles["TableHeader"]),
        Paragraph("<b>Source</b>", styles["TableHeader"]),
    ]
    data: List[List[Any]] = [headers]

    for row in rows:
        res = str(row.get("result") or "").upper()
        if res == "PASS":
            res_p = Paragraph(f"<b>{_clean(res)}</b>", styles["PassCell"])
        elif res in ("FAIL", "NON_COMPLIANT"):
            res_p = Paragraph(f"<b>{_clean(res)}</b>", styles["FailCell"])
        else:
            res_p = Paragraph(_clean(row.get("result")), styles["TableCell"])

        data.append([
            Paragraph(_clean(row.get("observation_id")), styles["TableCell"]),
            Paragraph(_clean(row.get("description")), styles["TableCell"]),
            res_p,
            Paragraph(_clean(row.get("data_source")), styles["TableCell"]),
        ])

    col_widths = [95, 210, 58, 160.27]
    table = Table(data, colWidths=col_widths)
    bg_color = COLOR_REJECTION_BG if is_rejection else COLOR_TH_BG

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), bg_color),
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_evidence_table(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> Any:
    rows = context.get("evidence") or []
    if not rows:
        return Paragraph("No evidence metadata supplied.", styles["TableCell"])

    headers = [
        Paragraph("<b>Reference</b>", styles["TableHeader"]),
        Paragraph("<b>Attachment</b>", styles["TableHeader"]),
        Paragraph("<b>Description</b>", styles["TableHeader"]),
        Paragraph("<b>Source</b>", styles["TableHeader"]),
    ]
    data: List[List[Any]] = [headers]

    for row in rows:
        data.append([
            Paragraph(_clean(row.get("evidence_id")), styles["TableCell"]),
            Paragraph(_clean(row.get("file_name")), styles["TableCell"]),
            Paragraph(_clean(row.get("description")), styles["TableCell"]),
            Paragraph(_clean(row.get("data_source")), styles["TableCell"]),
        ])

    col_widths = [95, 120, 155, 153.27]
    table = Table(data, colWidths=col_widths)

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_TH_BG),
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _build_test_list(items: Any, styles: Dict[str, ParagraphStyle]) -> Any:
    values = items if isinstance(items, list) else ([] if not items else [items])
    if not values:
        return Paragraph("Not supplied.", styles["TableCell"])

    flowables = []
    for v in values:
        flowables.append(Paragraph(f"• {_clean(v)}", styles["TableCell"]))
    return flowables


def _build_signature_block(styles: Dict[str, ParagraphStyle]) -> Table:
    box1 = Paragraph(
        "Prepared by: ________________________<br/>"
        "Signature / reference: ________________________",
        styles["SignatureText"],
    )
    box2 = Paragraph(
        "Technical review / approval: ________________________<br/>"
        "Date: ________________________",
        styles["SignatureText"],
    )
    table = Table([[box1, box2]], colWidths=[USABLE_WIDTH * 0.5, USABLE_WIDTH * 0.5])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_TH_BG),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return table


def _section(
    title: str,
    content: Any,
    styles: Dict[str, ParagraphStyle],
    is_rejection: bool = False,
) -> List[Any]:
    heading_style = styles["RejectionSectionHeading"] if is_rejection else styles["SectionHeading"]
    elements: List[Any] = [
        Paragraph(_clean(title), heading_style),
    ]
    if isinstance(content, list):
        elements.extend(content)
    else:
        elements.append(content)
    elements.append(Spacer(1, 6))
    return elements


def _build_oiml_flowables(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    report, job, inst = context["report"], context.get("job", {}), context.get("instrument", {})
    approval, results = context.get("approval", {}), context.get("results", {})

    flowables: List[Any] = []
    flowables.extend(_section(
        "Type Evaluation Identification",
        _build_key_value_table(_template_records(report, job) + [("Evaluation status", results.get("outcome"))], styles),
        styles,
    ))
    flowables.extend(_section(
        "Manufacturer / Model Identification",
        _build_key_value_table(_template_instrument(report, inst), styles),
        styles,
    ))
    flowables.extend(_section(
        "Model Approval / Reference Information",
        _build_key_value_table(_template_references(report, approval, results), styles),
        styles,
    ))
    flowables.extend(_section(
        "Metrological Characteristics",
        _build_key_value_table(_template_instrument(report, inst)[4:], styles),
        styles,
    ))
    flowables.extend(_section(
        "Applicable Test Programme",
        _build_test_list(job.get("applicable_tests"), styles),
        styles,
    ))
    flowables.extend(_section(
        "Test-Point / Evaluation Matrix",
        _build_observations_table(context.get("observations"), styles),
        styles,
    ))
    flowables.extend(_section(
        "MPE / Regulatory Reference Information",
        _build_key_value_table(_template_references(report, approval, results)[2:], styles),
        styles,
    ))
    flowables.extend(_section(
        "Observations and Evaluation Outcome",
        _build_key_value_table([
            ("Recorded outcome", results.get("outcome")),
            ("Observation source", "Labelled P4 adapter output is currently supplied."),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Evidence / Traceability",
        _build_evidence_table(context, styles),
        styles,
    ))
    flowables.extend(_section(
        "Review / Signature",
        [
            _build_key_value_table(_template_review(context), styles),
            Spacer(1, 6),
            _build_signature_block(styles),
        ],
        styles,
    ))
    return flowables


def _build_gatc_flowables(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    report, job, inst = context["report"], context.get("job", {}), context.get("instrument", {})
    approval, results = context.get("approval", {}), context.get("results", {})

    flowables: List[Any] = []
    flowables.extend(_section(
        "Verification Certificate Identification",
        _build_key_value_table(_template_records(report, job) + [("Certificate status", report.get("status"))], styles),
        styles,
    ))
    flowables.extend(_section(
        "Instrument Particulars",
        _build_key_value_table(_template_instrument(report, inst), styles),
        styles,
    ))
    flowables.extend(_section(
        "Model Approval Reference",
        _build_key_value_table(_template_references(report, approval, results)[:2], styles),
        styles,
    ))
    flowables.extend(_section(
        "GATC / Statutory Routing Reference",
        _build_key_value_table([
            ("GATC reference", approval.get("gatc_reference")),
            ("Testing centre", job.get("testing_centre_name")),
            ("Job routing", job.get("routing_decision")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Verification Test Plan",
        _build_test_list(job.get("applicable_tests"), styles),
        styles,
    ))
    flowables.extend(_section(
        "Verification Results",
        _build_observations_table(context.get("observations"), styles),
        styles,
    ))
    flowables.extend(_section(
        "MPE / Tolerance References",
        _build_key_value_table(_template_references(report, approval, results)[2:], styles),
        styles,
    ))
    flowables.extend(_section(
        "Inspector / Testing-Centre Information",
        _build_key_value_table([
            ("Inspector", job.get("assigned_inspector_name")),
            ("Testing centre", job.get("testing_centre_name")),
            ("Job status", job.get("status")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Decision / Status",
        _build_key_value_table([
            ("Recorded decision", results.get("outcome")),
            ("Report status", report.get("status")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Evidence / Reviewer",
        [
            _build_evidence_table(context, styles),
            Spacer(1, 6),
            _build_key_value_table(_template_review(context), styles),
        ],
        styles,
    ))
    flowables.extend(_section(
        "Certificate / Signature Area",
        _build_signature_block(styles),
        styles,
    ))
    return flowables


def _build_generic_flowables(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    report, job, inst = context["report"], context.get("job", {}), context.get("instrument", {})
    approval, results = context.get("approval", {}), context.get("results", {})

    flowables: List[Any] = []
    flowables.extend(_section(
        "Configurable Verification Record",
        _build_key_value_table(_template_records(report, job) + [("Report status", report.get("status"))], styles),
        styles,
    ))
    flowables.extend(_section(
        "Instrument Particulars",
        _build_key_value_table(_template_instrument(report, inst), styles),
        styles,
    ))
    flowables.extend(_section(
        "Applicable State / Regulatory Profile",
        _build_key_value_table(
            _template_references(report, approval, results)[:2]
            + [("Upstream references", ", ".join(approval.get("regulatory_rule_references") or []))],
            styles,
        ),
        styles,
    ))
    flowables.extend(_section(
        "Test Programme",
        _build_test_list(job.get("applicable_tests"), styles),
        styles,
    ))
    flowables.extend(_section(
        "Results and Tolerance Comparison",
        [
            _build_observations_table(context.get("observations"), styles),
            Spacer(1, 6),
            _build_key_value_table(_template_references(report, approval, results)[2:4], styles),
        ],
        styles,
    ))
    flowables.extend(_section(
        "Decision",
        _build_key_value_table([
            ("Recorded outcome", results.get("outcome")),
            ("Configurable record", "Not represented as one specific state's statutory form."),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Evidence",
        _build_evidence_table(context, styles),
        styles,
    ))
    flowables.extend(_section(
        "Reviewer / Signature",
        [
            _build_key_value_table(_template_review(context), styles),
            Spacer(1, 6),
            _build_signature_block(styles),
        ],
        styles,
    ))
    return flowables


def _build_rejection_flowables(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    report, job, inst = context["report"], context.get("job", {}), context.get("instrument", {})
    approval, results = context.get("approval", {}), context.get("results", {})

    flowables: List[Any] = []
    flowables.extend(_build_rejection_notice(results, styles))

    flowables.extend(_section(
        "Notice Identification",
        _build_key_value_table(_template_records(report, job) + [("Notice status", "REJECTION / NON-COMPLIANCE")], styles, is_rejection=True),
        styles,
        is_rejection=True,
    ))
    flowables.extend(_section(
        "Instrument / Job Particulars",
        _build_key_value_table(_template_instrument(report, inst) + [("Job status", job.get("status"))], styles),
        styles,
    ))
    flowables.extend(_section(
        "Test Programme",
        _build_test_list(job.get("applicable_tests"), styles),
        styles,
    ))
    flowables.extend(_section(
        "Rejection Decision",
        _build_key_value_table([
            ("Recorded decision", results.get("outcome")),
            ("Report status", report.get("status")),
        ], styles, is_rejection=True),
        styles,
        is_rejection=True,
    ))
    flowables.extend(_section(
        "Failed / Non-Compliant Criteria",
        [
            Paragraph("No unlabelled failure is asserted. Available adapter observations are listed below.", styles["TableCell"]),
            Spacer(1, 4),
            _build_observations_table(context.get("observations"), styles, is_rejection=True),
        ],
        styles,
        is_rejection=True,
    ))
    flowables.extend(_section(
        "Observed / Result Information",
        _build_key_value_table([
            ("Observation source", "Labelled P4 adapter output is currently supplied."),
            ("Recorded outcome", results.get("outcome")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Applicable MPE / Reference Information",
        _build_key_value_table(_template_references(report, approval, results)[2:], styles),
        styles,
    ))
    flowables.extend(_section(
        "Reason for Rejection",
        _build_key_value_table([
            ("Available reason", job.get("notes") or "Not supplied by upstream workflow."),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Required Corrective / Retest Action",
        Paragraph("Corrective action and retest requirements must be supplied by the responsible workflow; this template does not invent them.", styles["TableCell"]),
        styles,
    ))
    flowables.extend(_section(
        "Reviewer / Authority",
        _build_key_value_table(_template_review(context), styles),
        styles,
    ))
    flowables.extend(_section(
        "Evidence / Traceability",
        _build_evidence_table(context, styles),
        styles,
    ))
    flowables.extend(_section(
        "Notice / Signature Area",
        _build_signature_block(styles),
        styles,
        is_rejection=True,
    ))
    return flowables


def _build_annex_flowables(context: Dict[str, Any], styles: Dict[str, ParagraphStyle]) -> List[Any]:
    report, job, inst = context["report"], context.get("job", {}), context.get("instrument", {})
    environment = context.get("environment") or {}
    certificate = context.get("test_weight_certificate") or {}
    results = context.get("results") or {}

    flowables: List[Any] = []
    flowables.extend(_section(
        "Annex Identification",
        _build_key_value_table(_template_records(report, job) + [("Parent report / job reference", report.get("report_number") or job.get("job_number"))], styles),
        styles,
    ))
    flowables.extend(_section(
        "Instrument Identification",
        _build_key_value_table(_template_instrument(report, inst), styles),
        styles,
    ))
    flowables.extend(_section(
        "Evidence Index",
        _build_evidence_table(context, styles),
        styles,
    ))
    flowables.extend(_section(
        "Observation References",
        _build_observations_table(context.get("observations"), styles),
        styles,
    ))
    flowables.extend(_section(
        "Environmental Records",
        _build_key_value_table([
            ("Temperature", environment.get("temperature")),
            ("Humidity", environment.get("humidity")),
            ("Record note", environment.get("note")),
            ("Source", environment.get("data_source")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Test-Weight / Calibration Certificate References",
        _build_key_value_table([
            ("Certificate number", certificate.get("certificate_number")),
            ("Reference note", certificate.get("note")),
            ("Source", certificate.get("data_source")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Reviewer / Evidence Metadata",
        _build_key_value_table(_template_review(context), styles),
        styles,
    ))
    flowables.extend(_section(
        "Traceability / Audit Information",
        _build_key_value_table([
            ("Job state-history entries", len(job.get("state_history") or [])),
            ("Applicable tests", ", ".join(job.get("applicable_tests") or [])),
            ("MPE reference", results.get("mpe_reference")),
            ("MPE information supplied", results.get("mpe_information")),
        ], styles),
        styles,
    ))
    flowables.extend(_section(
        "Attachment / Reference Section",
        Paragraph("Attachment references above are metadata only. Any DEMO/MOCK entry is not a measured, reviewed, or issued record.", styles["TableCell"]),
        styles,
    ))
    return flowables


BUILDERS = {
    "OIML_R76_2_TYPE_EVALUATION": _build_oiml_flowables,
    "GATC_THIRD_SCHEDULE_VERIFICATION": _build_gatc_flowables,
    "GENERIC_VERIFICATION": _build_generic_flowables,
    "REJECTION_DOCUMENT": _build_rejection_flowables,
    "TECHNICAL_EVIDENCE_ANNEX": _build_annex_flowables,
}


def render_report_pdf(context: Dict[str, Any]) -> bytes:
    """Render a high-fidelity, type-specific PDF document for the given report context."""
    report = context["report"]
    report_type = str(report.get("report_type"))
    title = TITLES.get(report_type, report_type.replace("_", " "))
    subtitle = SUBTITLES.get(report_type, "Backend-generated report snapshot.")
    contains_demo = bool(context.get("contains_demo_data"))

    styles = _make_styles()
    story: List[Any] = []

    # 1. Header with branding, titles, metadata and badge
    story.extend(_build_header(report, title, subtitle, contains_demo, styles))

    # 2. Body sections specific to the canonical report type
    builder = BUILDERS.get(report_type, _build_generic_flowables)
    story.extend(builder(context, styles))

    # 3. Compile PDF into memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=38,
        title=str(report.get("report_number") or "MetrIQ Report"),
        author="MetrIQ NAWI Verification Platform",
        subject=title,
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
