from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
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
_BLUE = colors.HexColor("#2563EB")
_TEAL = colors.HexColor("#0F766E")
_PALE_BLUE = colors.HexColor("#EAF1F8")
_PALE_TEAL = colors.HexColor("#E7F4F1")
_TEXT = colors.HexColor("#263445")
_MUTED = colors.HexColor("#64748B")
_GRID = colors.HexColor("#D8E0E8")


def _percent(part: int, total: int) -> str:
    return f"{(part / total * 100) if total else 0:.1f}%"


def _bar_chart(
    labels: list[str],
    values: list[int],
    color: colors.Color,
    width: float,
) -> Drawing:
    chart_height = max(3.3 * cm, len(labels) * 0.72 * cm + 0.45 * cm)
    drawing = Drawing(width, chart_height)
    label_width = 4.8 * cm
    top = chart_height - 0.3 * cm
    row_height = (chart_height - 0.45 * cm) / max(len(labels), 1)
    max_value = max(values, default=0)
    bar_width = width - label_width - 1.2 * cm

    for index, (label, value) in enumerate(zip(labels, values)):
        y = top - (index + 1) * row_height + 0.2 * cm
        drawing.add(String(0, y + 0.04 * cm, label, fontName="Helvetica", fontSize=7, fillColor=_TEXT))
        current_bar_width = bar_width * value / max_value if max_value else 0
        if current_bar_width:
            drawing.add(Rect(
                label_width,
                y,
                current_bar_width,
                0.32 * cm,
                fillColor=color,
                strokeColor=None,
                rx=2,
                ry=2,
            ))
        value_x = label_width + current_bar_width + 0.18 * cm
        drawing.add(
            String(value_x, y + 0.04 * cm, f"{value:,}".replace(",", "."), fontName="Helvetica-Bold", fontSize=7, fillColor=_TEXT)
        )
    return drawing


def _draw_footer(canvas, document) -> None:
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(_NAVY)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(page_width / 2, page_height - 0.85 * cm, "Diretoria de TI")
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(
        page_width / 2,
        page_height - 1.25 * cm,
        "Gerência de Administração de Sistemas em TI",
    )
    canvas.setStrokeColor(_GRID)
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, page_height - 1.55 * cm, page_width - document.rightMargin, page_height - 1.55 * cm)
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
    units_with = stats["units_with_inconsistencies"]
    units_without = stats["units_without_inconsistencies"]
    by_type = stats["by_type"]
    per_school = stats["per_school"]

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=2.0 * cm,
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
        textColor=_NAVY,
        alignment=TA_LEFT,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="ReportSubtitle",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=_MUTED,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11,
        textColor=_NAVY,
        spaceBefore=5,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="MetricValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=16,
        textColor=_NAVY,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="MetricLabel",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=_MUTED,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableHeaderSmall",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=5.8,
        leading=6.8,
        textColor=colors.white,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="TableCellSmall",
        parent=styles["Normal"],
        fontSize=6.2,
        leading=7.2,
        textColor=_TEXT,
    ))

    metrics = [
        [
            Paragraph(f"{units_without:,}".replace(",", "."), styles["MetricValue"]),
            Paragraph(f"{units_with:,}".replace(",", "."), styles["MetricValue"]),
            Paragraph(f"{total_units:,}".replace(",", "."), styles["MetricValue"]),
        ],
        [
            Paragraph(
                f"Unidades sem inconsistências<br/><b>{_percent(units_without, total_units)}</b> do total",
                styles["MetricLabel"],
            ),
            Paragraph(
                f"Unidades com inconsistências<br/><b>{_percent(units_with, total_units)}</b> do total",
                styles["MetricLabel"],
            ),
            Paragraph("Unidades escolares analisadas", styles["MetricLabel"]),
        ],
    ]
    metrics_table = Table(
        metrics,
        colWidths=[document.width / 3] * 3,
        rowHeights=[0.8 * cm, 0.85 * cm],
    )
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), _PALE_TEAL),
        ("BACKGROUND", (1, 0), (1, -1), _PALE_BLUE),
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
    units_by_type = [item["units"] for item in by_type.values()]
    issues_by_type = [item["issues"] for item in by_type.values()]

    story = [
        Paragraph("Resumo analítico de Inconsistências - Educacenso", styles["ReportTitle"]),
        Paragraph(
            f"Gerado em {datetime.now():%d/%m/%Y %H:%M} · "
            "Os totais consideram os relatórios enviados; categorias marcadas como não utilizadas "
            "não entram na contagem.",
            styles["ReportSubtitle"],
        ),
        metrics_table,
        Spacer(1, 0.25 * cm),
        Paragraph("Unidades com inconsistências por tipo de relatório", styles["SectionTitle"]),
        _bar_chart(type_labels, units_by_type, _BLUE, available_chart_width),
        Paragraph("Total de inconsistências por tipo de relatório", styles["SectionTitle"]),
        _bar_chart(type_labels, issues_by_type, _TEAL, available_chart_width),
        PageBreak(),
        Paragraph("Inconsistências por unidade escolar", styles["ReportTitle"]),
        Paragraph(
            "O total por unidade corresponde à soma das linhas de inconsistência nos relatórios utilizados.",
            styles["ReportSubtitle"],
        ),
    ]

    headers = [
        "Unidade Escolar",
        "Código INEP",
        "Total",
        *[item["label"] for item in by_type.values()],
    ]
    detail_rows = [[Paragraph(header, styles["TableHeaderSmall"]) for header in headers]]
    for school in per_school:
        detail_rows.append([
            Paragraph(escape(school["nome_unidade"]), styles["TableCellSmall"]),
            Paragraph(school["codigo_inep"], styles["TableCellSmall"]),
            str(school["total_issues"]),
            *[str(school["by_type"][key]) for key in by_type],
        ])

    detail_table = Table(
        detail_rows,
        colWidths=[
            4.5 * cm,
            1.55 * cm,
            0.85 * cm,
            *[2.15 * cm] * len(by_type),
        ],
        repeatRows=1,
        hAlign="LEFT",
    )
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
        ("GRID", (0, 0), (-1, -1), 0.35, _GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(detail_table)

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()


def statistics_pdf_filename() -> str:
    return f"resumo_analitico_inconsistencias_{date.today():%d-%m-%Y}.pdf"
