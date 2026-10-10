from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path
from typing import Any

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


_NAVY = colors.HexColor("#16324F")
_BLUE = colors.HexColor("#6FA8DC")
_TEAL = colors.HexColor("#77C593")
_TEXT = colors.black
_MUTED = colors.black
_GRID = colors.HexColor("#D8E0E8")
_ROW_ALT = colors.HexColor("#F7F9FC")
_BAR_TRACK = colors.HexColor("#EDF1F5")
_TOTAL_BADGE = colors.HexColor("#E8EEF5")
_CHART_FONT_SIZE = 7


def _percent(part: int, total: int) -> str:
    return f"{(part / total * 100) if total else 0:.1f}%"


def _school_type(name: str) -> str:
    normalized_name = name.strip().upper()
    if normalized_name == "CEMSTIAC":
        return "Escola"
    return "Creche" if normalized_name.startswith(("CEM", "CMEI")) else "Escola"


def _table_count(value: int) -> str:
    return "---" if value == 0 else str(value)


def _ordered_schools(schools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        schools,
        key=lambda school: (
            _school_type(school["nome_unidade"]) != "Creche",
            school["nome_unidade"].casefold(),
        ),
    )


def _counts_by_school_type(
    schools: list[dict[str, Any]],
    report_key: str,
) -> tuple[int, int]:
    counts = {"Creche": 0, "Escola": 0}
    for school in schools:
        counts[_school_type(school["nome_unidade"])] += school["by_type"][report_key]
    return counts["Creche"], counts["Escola"]


def _school_type_summary(schools: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary = {
        "Creche": {"total": 0, "with_inconsistencies": 0},
        "Escola": {"total": 0, "with_inconsistencies": 0},
    }
    for school in schools:
        school_type = _school_type(school["nome_unidade"])
        summary[school_type]["total"] += 1
        summary[school_type]["with_inconsistencies"] += int(school["total_issues"] > 0)
    for counts in summary.values():
        counts["without_inconsistencies"] = counts["total"] - counts["with_inconsistencies"]
    return summary


def _split_bar_chart(
    labels: list[str],
    values_by_type: list[tuple[int, int]],
    width: float,
) -> Drawing:
    chart_height = max(5.0 * cm, len(labels) * 0.9 * cm + 1.15 * cm)
    drawing = Drawing(width, chart_height)
    label_width = 4.25 * cm
    total_width = 1.45 * cm
    column_gap = 0.28 * cm
    bar_width = width - label_width - total_width - column_gap - 0.2 * cm
    rows_bottom = 0.45 * cm
    rows_top = chart_height - 0.92 * cm
    row_height = (rows_top - rows_bottom) / max(len(labels), 1)
    max_value = max((sum(values) for values in values_by_type), default=0)

    header_y = chart_height - 0.58 * cm
    drawing.add(String(
        0.12 * cm,
        header_y,
        "RELATÓRIO",
        fontName="Helvetica-Bold",
        fontSize=_CHART_FONT_SIZE,
        fillColor=_MUTED,
    ))
    drawing.add(String(
        label_width,
        header_y,
        "DISTRIBUIÇÃO POR TIPO DE UNIDADE",
        fontName="Helvetica-Bold",
        fontSize=_CHART_FONT_SIZE,
        fillColor=_MUTED,
    ))
    drawing.add(String(
        width - total_width / 2,
        header_y,
        "TOTAL",
        fontName="Helvetica-Bold",
        fontSize=_CHART_FONT_SIZE,
        fillColor=_MUTED,
        textAnchor="middle",
    ))

    for index, (label, values) in enumerate(zip(labels, values_by_type)):
        creche_count, school_count = values
        total = creche_count + school_count
        row_bottom = rows_top - (index + 1) * row_height
        center_y = row_bottom + row_height / 2
        bar_height = 0.43 * cm
        bar_y = center_y - bar_height / 2
        if index % 2:
            drawing.add(Rect(
                0,
                row_bottom,
                width,
                row_height,
                fillColor=_ROW_ALT,
                strokeColor=None,
            ))
        drawing.add(String(
            0.12 * cm,
            center_y - 2.5,
            label,
            fontName="Helvetica-Bold",
            fontSize=_CHART_FONT_SIZE,
            fillColor=_TEXT,
        ))
        drawing.add(Rect(
            label_width,
            bar_y,
            bar_width,
            bar_height,
            fillColor=_BAR_TRACK,
            strokeColor=None,
            rx=3,
            ry=3,
        ))
        total_bar_width = bar_width * total / max_value if max_value else 0
        creche_width = total_bar_width * creche_count / total if total else 0
        school_width = total_bar_width - creche_width
        if creche_width:
            drawing.add(Rect(
                label_width,
                bar_y,
                creche_width,
                bar_height,
                fillColor=_BLUE,
                strokeColor=None,
            ))
        if school_width:
            drawing.add(Rect(
                label_width + creche_width,
                bar_y,
                school_width,
                bar_height,
                fillColor=_TEAL,
                strokeColor=None,
            ))

        for count, segment_start, segment_width in (
            (creche_count, label_width, creche_width),
            (school_count, label_width + creche_width, school_width),
        ):
            if not segment_width:
                continue
            text = str(count)
            if stringWidth(text, "Helvetica-Bold", _CHART_FONT_SIZE) <= segment_width - 3:
                drawing.add(String(
                    segment_start + segment_width / 2,
                    center_y - 2.3,
                    text,
                    fontName="Helvetica-Bold",
                    fontSize=_CHART_FONT_SIZE,
                    fillColor=_TEXT,
                    textAnchor="middle",
                ))
        badge_x = width - total_width + 0.12 * cm
        badge_width = total_width - 0.24 * cm
        badge_height = 0.52 * cm
        drawing.add(Rect(
            badge_x,
            center_y - badge_height / 2,
            badge_width,
            badge_height,
            fillColor=_TOTAL_BADGE,
            strokeColor=None,
            rx=4,
            ry=4,
        ))
        drawing.add(String(
            badge_x + badge_width / 2,
            center_y - 2.5,
            f"{total}",
            fontName="Helvetica-Bold",
            fontSize=_CHART_FONT_SIZE,
            fillColor=colors.black,
            textAnchor="middle",
        ))
        drawing.add(Rect(
            0,
            row_bottom,
            width,
            0.3,
            fillColor=_GRID,
            strokeColor=None,
        ))

    legend_y = 0.12 * cm
    legend_x = label_width
    drawing.add(Rect(legend_x, legend_y, 0.22 * cm, 0.22 * cm, fillColor=_BLUE, strokeColor=None))
    drawing.add(String(legend_x + 0.3 * cm, legend_y + 0.03 * cm, "Creche", fontName="Helvetica", fontSize=_CHART_FONT_SIZE, fillColor=_TEXT))
    drawing.add(Rect(legend_x + 1.4 * cm, legend_y, 0.22 * cm, 0.22 * cm, fillColor=_TEAL, strokeColor=None))
    drawing.add(String(legend_x + 1.7 * cm, legend_y + 0.03 * cm, "Escola", fontName="Helvetica", fontSize=_CHART_FONT_SIZE, fillColor=_TEXT))
    return drawing


def _draw_page_header_footer(canvas, document) -> None:
    canvas.saveState()
    page_width, page_height = A4
    image_directory = Path(__file__).resolve().parents[3] / "imagem"
    crest = ImageReader(str(image_directory / "brasao.png"))
    crest_width = 1.5 * cm
    crest_height = 1.7 * cm
    canvas.drawImage(
        crest,
        document.leftMargin,
        page_height - 1.75 * cm,
        width=crest_width,
        height=crest_height,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    text_x = document.leftMargin + 1.8 * cm
    canvas.setFillColor(_NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(
        text_x,
        page_height - 0.78 * cm,
        "Secretaria Municipal de Educação, Ciência e Tecnologia",
    )
    canvas.setFont("Helvetica", 8.5)
    canvas.drawString(text_x, page_height - 1.15 * cm, "Diretoria de TI")
    canvas.drawString(
        text_x,
        page_height - 1.52 * cm,
        "Gerência de Administração de Sistemas de TI",
    )
    logo = ImageReader(str(image_directory / "image.png"))
    logo_width = 2.7 * cm
    logo_height = 1.3 * cm
    canvas.drawImage(
        logo,
        page_width - document.rightMargin - logo_width,
        page_height - 1.55 * cm,
        width=logo_width,
        height=logo_height,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )
    canvas.setStrokeColor(_GRID)
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, page_height - 1.85 * cm, page_width - document.rightMargin, page_height - 1.85 * cm)
    canvas.setStrokeColor(_GRID)
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, 0.95 * cm, page_width - document.rightMargin, 0.95 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_MUTED)
    canvas.drawString(document.leftMargin, 0.62 * cm, "Resumo analítico de Inconsistências - Educacenso")
    canvas.drawRightString(page_width - document.rightMargin, 0.62 * cm, f"Página {document.page}")
    canvas.restoreState()


def build_statistics_pdf(stats: dict[str, Any]) -> bytes:
    total_units = stats["total_units"]
    by_type = stats["by_type"]
    per_school = stats["per_school"]

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=2.2 * cm,
        bottomMargin=1.35 * cm,
        title="Resumo analítico de Inconsistências - Educacenso",
        author="Aplicações de Apoio - Censo Escolar",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.black,
        alignment=TA_LEFT,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=colors.black,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11,
        textColor=colors.black,
        spaceBefore=5,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="MetricValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=colors.black,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="MetricLabel",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=colors.black,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableHeaderSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.4,
        textColor=colors.white,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableCellSmall",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.4,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        name="TableCellCentered",
        parent=styles["TableCellSmall"],
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableCellBoldCentered",
        parent=styles["TableCellCentered"],
        fontName="Helvetica-Bold",
    ))

    school_summary = _school_type_summary(per_school)
    metrics = [
        [
            Paragraph(
                f"{school_summary['Creche']['total']:,}".replace(",", "."),
                styles["MetricValue"],
            ),
            Paragraph(
                f"{school_summary['Escola']['total']:,}".replace(",", "."),
                styles["MetricValue"],
            ),
            Paragraph(
                f"{total_units:,}".replace(",", "."),
                styles["MetricValue"],
            ),
        ],
        [
            Paragraph(
                f"<b>Creches</b><br/>"
                f"Com inconsistências: {school_summary['Creche']['with_inconsistencies']} "
                f"({_percent(school_summary['Creche']['with_inconsistencies'], school_summary['Creche']['total'])})<br/>"
                f"Sem inconsistências: {school_summary['Creche']['without_inconsistencies']} "
                f"({_percent(school_summary['Creche']['without_inconsistencies'], school_summary['Creche']['total'])})",
                styles["MetricLabel"],
            ),
            Paragraph(
                f"<b>Escolas</b><br/>"
                f"Com inconsistências: {school_summary['Escola']['with_inconsistencies']} "
                f"({_percent(school_summary['Escola']['with_inconsistencies'], school_summary['Escola']['total'])})<br/>"
                f"Sem inconsistências: {school_summary['Escola']['without_inconsistencies']} "
                f"({_percent(school_summary['Escola']['without_inconsistencies'], school_summary['Escola']['total'])})",
                styles["MetricLabel"],
            ),
            Paragraph(
                f"<b>Total geral</b><br/>"
                f"Com inconsistências: {stats['units_with_inconsistencies']} "
                f"({_percent(stats['units_with_inconsistencies'], total_units)})<br/>"
                f"Sem inconsistências: {stats['units_without_inconsistencies']} "
                f"({_percent(stats['units_without_inconsistencies'], total_units)})",
                styles["MetricLabel"],
            ),
        ],
    ]
    metrics_table = Table(
        metrics,
        colWidths=[document.width / 3] * 3,
        rowHeights=[0.8 * cm, 1.35 * cm],
    )
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _BLUE),
        ("BACKGROUND", (1, 0), (1, -1), _TEAL),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.6, _GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    available_chart_width = document.width
    type_labels = [
        f"{item['label']} (não utilizado)" if not item["used"] else item["label"]
        for item in by_type.values()
    ]
    report_keys = list(by_type)
    issues_by_type = [
        _counts_by_school_type(per_school, key)
        for key in report_keys
    ]

    story = [
        Paragraph("Resumo analítico de Inconsistências - Educacenso", styles["ReportTitle"]),
        Paragraph(
            f"Gerado em {datetime.now():%d/%m/%Y %H:%M}",
            styles["ReportSubtitle"],
        ),
        metrics_table,
        Spacer(1, 1.25 * cm),
        Paragraph("Total de inconsistências por tipo de relatório", styles["SectionTitle"]),
        _split_bar_chart(type_labels, issues_by_type, available_chart_width),
        PageBreak(),
        Paragraph("Inconsistências por unidade escolar", styles["ReportTitle"]),
        Paragraph(
            "O total por unidade corresponde à soma das linhas de inconsistência nos relatórios utilizados.",
            styles["ReportSubtitle"],
        ),
    ]

    headers = [
        "Tipo",
        "Nome",
        "Código INEP",
        "Total de Inconsistências",
        *[item["label"] for item in by_type.values()],
    ]
    category_start = 4
    detail_rows = [
        [
            *[
                Paragraph(header, styles["TableHeaderSmall"])
                for header in headers[:category_start]
            ],
            Paragraph(
                "Inconsistências separadas por tipo",
                styles["TableHeaderSmall"],
            ),
            *[None] * (len(headers) - category_start - 1),
        ],
        [
            *[None] * category_start,
            *[
                Paragraph(header, styles["TableHeaderSmall"])
                for header in headers[category_start:]
            ],
        ],
    ]
    for school in _ordered_schools(per_school):
        total_issues = school["total_issues"]
        detail_rows.append([
            Paragraph(_school_type(school["nome_unidade"]), styles["TableCellSmall"]),
            Paragraph(escape(school["nome_unidade"]), styles["TableCellSmall"]),
            Paragraph(school["codigo_inep"], styles["TableCellCentered"]),
            Paragraph(
                _table_count(total_issues),
                styles[
                    "TableCellBoldCentered"
                    if total_issues
                    else "TableCellCentered"
                ],
            ),
            *[
                Paragraph(
                    _table_count(school["by_type"][key]),
                    styles["TableCellCentered"],
                )
                for key in by_type
            ],
        ])

    detail_table = Table(
        detail_rows,
        colWidths=[
            1.4 * cm,
            3.4 * cm,
            1.5 * cm,
            2.6 * cm,
            *[(document.width - 8.9 * cm) / len(by_type)] * len(by_type),
        ],
        repeatRows=2,
        hAlign="LEFT",
    )
    detail_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (0, 1)),
        ("SPAN", (1, 0), (1, 1)),
        ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (category_start, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), _NAVY),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
        ("GRID", (0, 0), (-1, -1), 0.35, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(detail_table)

    document.build(
        story,
        onFirstPage=_draw_page_header_footer,
        onLaterPages=_draw_page_header_footer,
    )
    return buffer.getvalue()


def statistics_pdf_filename() -> str:
    return f"resumo_analitico_inconsistencias_{date.today():%d-%m-%Y}.pdf"
