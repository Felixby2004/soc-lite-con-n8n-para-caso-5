"""Reportes del entrenamiento a partir del resultado guardado."""
from io import BytesIO

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from openpyxl import Workbook
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.styles import Font

from app.schemas.access_evaluation import EvaluationFormat
from app.services.access_evaluation_report import percentage, render_docx_sections, render_pdf_sections

TITLE = "Evaluación de modelos de acceso"
FIGURE_TITLE = "Curvas ROC y precisión sensibilidad"
METHOD = (
    "Desarrollo, validación y prueba se separaron por días UTC. Optuna optimizó la precisión promedio en tres pliegues "
    "internos por cada uno de los cinco pliegues externos. El umbral se eligió en validación. "
    "Las métricas y curvas corresponden a prueba. La comparación pareada usa bloques por día UTC."
)
PARTITIONS = {"development": "Desarrollo", "validation": "Validación", "test": "Prueba"}
ALGORITHMS = {"logistic": "Regresión logística", "tree": "Árbol de decisión"}
MODEL_COLOR = "#087f8c"
HEURISTIC_COLOR = "#b76230"


def report_tables(result: dict):
    yield "Particiones", (
        ("Partición", "Eventos", "Esperados", "Anómalos", "Días UTC"),
        *((PARTITIONS[key], part["events"], part["expected"], part["anomalous"], part["days"])
          for key, part in result["partitions"].items()),
    )
    yield "Métricas en prueba", (
        ("Métrica", "Modelo", "Heurística"),
        *((label, percentage(result["model"][key]), percentage(result["heuristic"][key])) for label, key in (
            ("ROC AUC", "roc_auc"), ("Precisión promedio", "average_precision"), ("Precisión al umbral", "precision"),
            ("Sensibilidad", "recall"), ("Especificidad", "specificity"), ("F1", "f1"), ("Exactitud", "accuracy"),
        )),
        ("Umbral del puntaje", f'{result["model"]["threshold"]:.4f}', "50/100"),
    )
    yield "Matrices de confusión", (
        ("Método", "VP", "FP", "FN", "VN"),
        *((name, *(result[key]["confusion"][cell] for cell in
                   ("true_positive", "false_positive", "false_negative", "true_negative")))
          for key, name in (("model", "Modelo"), ("heuristic", "Heurística"))),
    )
    yield "Validación cruzada externa", (
        ("Pliegue", "Desarrollo", "Validación", "Precisión promedio"),
        *((fold["fold"], fold["train"]["events"], fold["validation"]["events"], percentage(fold["average_precision"]))
          for fold in result["outer_folds"]),
        ("Promedio", "", "", percentage(result["mean_outer_ap"])),
    )
    paired = result["paired"]
    interval = paired["interval"]
    yield "Comparación pareada", (
        ("Medida", "Valor"),
        ("Diferencia de exactitud", f'{paired["difference"] * 100:.1f} pp'),
        ("Intervalo bootstrap 95 %", " a ".join(f"{value * 100:.1f} pp" for value in interval) if interval else "Sin base"),
        ("p por permutación de signos", f'{paired["p_value"]:.4f}' if paired["p_value"] is not None else "Sin base"),
        ("Bloques y réplicas", f'{paired["days"]} días UTC / {paired["replicates"]} réplicas'),
    )
    yield "Configuración elegida", (
        ("Parámetro", "Valor"),
        *((key, "Sin ponderación" if value is None else str(value)) for key, value in result["best_params"].items()),
        ("scikit-learn / Optuna", f'{result["versions"]["scikit_learn"]} / {result["versions"]["optuna"]}'),
    )


def curve_figure(result: dict) -> BytesIO:
    figure = Figure(figsize=(6.6, 2.05), dpi=600, layout="constrained")
    FigureCanvasAgg(figure)
    for axis, curve, xlabel, ylabel in (
        (figure.add_subplot(121), "roc", "Tasa de falsos positivos", "Sensibilidad"),
        (figure.add_subplot(122), "pr", "Sensibilidad", "Precisión"),
    ):
        for model, name, color in (("model", "Modelo", MODEL_COLOR), ("heuristic", "Heurística", HEURISTIC_COLOR)):
            points = result[model][curve]
            axis.plot([p["x"] for p in points], [p["y"] for p in points], color=color, label=name)
        axis.set(xlim=(0, 1), ylim=(0, 1.02), xlabel=xlabel, ylabel=ylabel)
        axis.tick_params(labelsize=7)
        axis.legend(fontsize=7, loc="lower right")
    figure.axes[0].plot([0, 1], [0, 1], linestyle=":", color="#75849b")
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=600)
    buffer.seek(0)
    return buffer


def render_workbook(context: str, result: dict) -> bytes:
    book = Workbook()
    overview = book.active
    overview.title = "Evaluación"
    overview.append([TITLE])
    overview.append([context])
    overview.append([METHOD])
    overview.append(["SHA-256 de la muestra", result["dataset_sha256"]])
    overview.column_dimensions["A"].width = 115
    for heading, rows in report_tables(result):
        sheet = book.create_sheet(heading)
        for row in rows:
            sheet.append(row)
        sheet.column_dimensions["A"].width = 35
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
    metrics = book["Métricas en prueba"]
    for row, key in enumerate(("roc_auc", "average_precision", "precision", "recall", "specificity", "f1", "accuracy"), 2):
        for column, method in enumerate(("model", "heuristic"), 2):
            value = result[method][key]
            if value is not None:
                metrics.cell(row, column, value).number_format = "0.0%"
    for curve, xlabel, ylabel in (("roc", "Tasa de falsos positivos", "Sensibilidad"), ("pr", "Sensibilidad", "Precisión")):
        sheet = book.create_sheet(curve.upper())
        chart = ScatterChart()
        chart.scatterStyle = "line"
        chart.title, chart.x_axis.title, chart.y_axis.title = curve.upper(), xlabel, ylabel
        for first, method, name in ((1, "model", "Modelo"), (4, "heuristic", "Heurística")):
            points = result[method][curve]
            sheet.cell(1, first, xlabel)
            sheet.cell(1, first + 1, ylabel)
            for row, point in enumerate(points, 2):
                sheet.cell(row, first, point["x"])
                sheet.cell(row, first + 1, point["y"])
            x = Reference(sheet, min_col=first, min_row=2, max_row=len(points) + 1)
            y = Reference(sheet, min_col=first + 1, min_row=2, max_row=len(points) + 1)
            chart.series.append(Series(y, x, title=name))
        sheet.add_chart(chart, "G2")
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def render_model_report(run_id: int, config: dict, result: dict, format: EvaluationFormat) -> bytes:
    scope = "Muestra simulada" if config["scope"] == "demo" else "Eventos operativos revisados"
    context = f"Ejecución {run_id}. {scope}. {ALGORITHMS[config['algorithm']]}. {config['trials']} ensayos por búsqueda."
    if format == "xlsx":
        return render_workbook(context, result)
    renderer = render_pdf_sections if format == "pdf" else render_docx_sections
    return renderer(TITLE, context, METHOD, report_tables(result), FIGURE_TITLE, curve_figure(result))
