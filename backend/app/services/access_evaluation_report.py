"""Exporta los resultados agregados sin incluir cuentas ni direcciones IP."""
from io import BytesIO

from docx import Document
from docx.shared import Inches
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.access_evaluation import AccessEvaluation, EvaluationFormat
from app.services.report_service import COLOR_ACCENT, COLOR_PRIMARY

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
TITLE = "Evaluación de accesos del Caso 5"
METHOD_NOTE = (
    "La matriz y las métricas usan solo los accesos con etiqueta de referencia. "
    "El umbral de evaluación se aplica al puntaje guardado. "
    "Los valores sin denominador figuran como sin base."
)


def scope_text(result: AccessEvaluation) -> str:
    if result.from_at is None:
        return "Demostración simulada. Etiquetas fijas de la muestra completa."
    return f"Operación. Del {result.from_at:%Y-%m-%d %H:%M} al {result.to_at:%Y-%m-%d %H:%M} UTC."


def percentage(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "Sin base"


def tables(result: AccessEvaluation):
    matrix = result.confusion
    yield "Resumen", (
        ("Indicador", "Valor"),
        ("Eventos evaluados", result.events),
        ("Eventos con etiqueta", result.reviewed),
        ("Marcados al umbral elegido", result.flagged),
        ("Umbral elegido / operativo", f"{result.threshold} / {result.live_threshold}"),
    )
    yield "Matriz de confusión", (
        ("Referencia", "Marcado", "Sin marcar"),
        ("Anómalo", matrix.true_positive, matrix.false_negative),
        ("Esperado", matrix.false_positive, matrix.true_negative),
    )
    yield "Métricas", (
        ("Medida", "Resultado"),
        ("Precisión", percentage(result.precision)),
        ("Sensibilidad", percentage(result.recall)),
        ("Especificidad", percentage(result.specificity)),
        ("F1", percentage(result.f1)),
    )
    yield "Cobertura de datos", (
        ("Campo disponible", "Eventos"),
        *((item.label, item.count) for item in result.data_quality),
    )


def score_figure(result: AccessEvaluation) -> BytesIO:
    figure = Figure(figsize=(6.6, 2.05), dpi=600, layout="constrained")
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    bars = axis.bar(
        [item.label for item in result.score_bands], [item.count for item in result.score_bands],
        color=COLOR_ACCENT, width=0.62,
    )
    axis.bar_label(bars, padding=2, fontsize=8)
    axis.set_ylim(0, max(1, *(item.count for item in result.score_bands)) * 1.22)
    axis.set_ylabel("Eventos", fontsize=8)
    axis.tick_params(labelsize=8)
    axis.spines[["top", "right"]].set_visible(False)
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=600)
    buffer.seek(0)
    return buffer


def render_pdf(result: AccessEvaluation) -> bytes:
    return render_pdf_sections(TITLE, scope_text(result), METHOD_NOTE, tables(result), "Distribución de puntajes", score_figure(result))


def render_pdf_sections(title, context, method, sections, figure_title, figure) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(title, styles["Title"]), Paragraph(context, styles["Normal"]),
        Spacer(1, 5), Paragraph(method, styles["Normal"]),
    ]
    for heading, rows in sections:
        elements.append(Paragraph(heading, styles["Heading2"]))
        table = Table(rows, colWidths=[480 / len(rows[0])] * len(rows[0]), hAlign="LEFT", repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(COLOR_PRIMARY)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f1f5f9"), colors.white]),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        elements.append(table)
    elements.extend([
        Paragraph(figure_title, styles["Heading2"]),
        Image(figure, width=480, height=149, hAlign="LEFT"),
    ])
    SimpleDocTemplate(
        output, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=40, bottomMargin=40,
        title=title,
    ).build(elements)
    return output.getvalue()


def render_docx(result: AccessEvaluation) -> bytes:
    return render_docx_sections(TITLE, scope_text(result), METHOD_NOTE, tables(result), "Distribución de puntajes", score_figure(result))


def render_docx_sections(title, context, method, sections, figure_title, figure) -> bytes:
    doc = Document()
    doc.add_paragraph(title, style="Title")
    doc.add_paragraph(context)
    doc.add_paragraph(method)
    for heading, rows in sections:
        doc.add_heading(heading, 1)
        table = doc.add_table(rows=0, cols=len(rows[0]))
        table.style = "Light Shading Accent 1"
        for row in rows:
            for cell, value in zip(table.add_row().cells, row):
                cell.text = str(value)
    doc.add_heading(figure_title, 1)
    doc.add_picture(figure, width=Inches(6))
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def render_xlsx(result: AccessEvaluation) -> bytes:
    workbook = Workbook()
    overview = workbook.active
    overview.title = "Evaluación"
    overview.append([TITLE])
    overview.append([scope_text(result)])
    overview.append([METHOD_NOTE])
    overview.column_dimensions["A"].width = 100
    for heading, rows in tables(result):
        sheet = workbook.create_sheet(heading)
        for row in rows:
            sheet.append(row)
        sheet.column_dimensions["A"].width = 43
        sheet.column_dimensions["B"].width = 21
        sheet.column_dimensions["C"].width = 21
        for cell in sheet[1]:
            cell.font = Font(color="FFFFFF", bold=True)
            cell.fill = PatternFill("solid", fgColor=COLOR_PRIMARY[1:])
        sheet.freeze_panes = "A2"
    metrics = workbook["Métricas"]
    for row, value in enumerate((result.precision, result.recall, result.specificity, result.f1), start=2):
        if value is not None:
            metrics.cell(row, 2, value).number_format = "0.0%"
    bands = workbook.create_sheet("Distribución")
    bands.append(["Puntaje", "Eventos"])
    for item in result.score_bands:
        bands.append([item.label, item.count])
    chart = BarChart()
    chart.title = "Distribución de puntajes"
    chart.y_axis.title = "Eventos"
    chart.add_data(Reference(bands, min_col=2, min_row=1, max_row=bands.max_row), titles_from_data=True)
    chart.set_categories(Reference(bands, min_col=1, min_row=2, max_row=bands.max_row))
    bands.add_chart(chart, "D2")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_evaluation(result: AccessEvaluation, format: EvaluationFormat) -> bytes:
    return {"pdf": render_pdf, "docx": render_docx, "xlsx": render_xlsx}[format](result)
