"""Informe de una hoja de validación.

build_report() arma una estructura de secciones a partir de los datos guardados
(reutilizando el motor de cálculo). Esa misma estructura se usa para la versión
imprimible en HTML y para el PDF generado con reportlab.
"""
import io
import math
from datetime import datetime

from app.models import ModuleData
from app.validation.modules import MODULES, compute


def _fmt(x, dec=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return "—" if not math.isfinite(x) else f"{x:.{dec}f}"
    return str(x)


def _table(head, rows):
    return {"type": "table", "head": head, "rows": rows}


def _kv(items):
    return {"type": "kv", "items": items}


def _caption(text):
    return {"type": "caption", "text": text}


def _data_blocks(kind, payload, unit):
    """Tabla(s) con los datos tal como se capturaron en el módulo."""
    if kind == "stats":
        levels = payload.get("levels", [])
        if not levels:
            return []
        head = [""] + [(lv.get("label") or f"Nivel {i + 1}") for i, lv in enumerate(levels)]
        rows = [[f"Nominal ({unit})"] + [lv.get("nominal", "") for lv in levels]]
        maxrep = max((len(lv.get("replicates", [])) for lv in levels), default=0)
        for r in range(maxrep):
            rows.append([f"Réplica {r + 1}"] +
                        [(lv.get("replicates", [])[r] if r < len(lv.get("replicates", [])) else "")
                         for lv in levels])
        return [_table(head, rows)]
    if kind == "curve":
        rows = [[f"Nivel {i + 1}", lv.get("nominal", ""), lv.get("response", "")]
                for i, lv in enumerate(payload.get("levels", []))]
        return [_table(["Nivel", f"Nominal ({unit})", "Respuesta"], rows)] if rows else []
    if kind == "suitability":
        inj = (payload.get("runs") or [{}])[0].get("injections", [])
        rows = [[f"Inyección {i + 1}", x.get("analyte", ""), x.get("is", "")] for i, x in enumerate(inj)]
        return [_table(["Inyección", "Área analito", "Área EI"], rows)] if rows else []
    if kind == "ratio":
        rows = [[f"Lote {i + 1}", r.get("blank_analyte", ""), r.get("ref_analyte", ""),
                 r.get("blank_is", ""), r.get("ref_is", "")] for i, r in enumerate(payload.get("rows", []))]
        return [_table(["Lote", "Blanco analito", "Ref. analito", "Blanco EI", "Ref. EI"], rows)] if rows else []
    if kind == "matrix":
        ref = payload.get("reference", {})
        out = [_kv([("Referencia · área analito", ref.get("analyte") or "—"),
                    ("Referencia · área EI", ref.get("is") or "—")])]
        rows = [[f"Lote {i + 1}", lt.get("analyte", ""), lt.get("is", "")]
                for i, lt in enumerate(payload.get("lots", []))]
        if rows:
            out.append(_table(["Lote", "Área analito (matriz)", "Área EI (matriz)"], rows))
        return out
    if kind == "recovery":
        levels = payload.get("levels", [])
        if not levels:
            return []
        head = ["Réplica"]
        for i, lv in enumerate(levels):
            lab = lv.get("label") or lv.get("id") or f"Nivel {i + 1}"
            head += [f"{lab} · sol", f"{lab} · matriz"]
        maxrep = max((max(len(lv.get("solution", [])), len(lv.get("matrix", []))) for lv in levels), default=0)
        rows = []
        for r in range(maxrep):
            row = [f"Réplica {r + 1}"]
            for lv in levels:
                sol, mat = lv.get("solution", []), lv.get("matrix", [])
                row += [sol[r] if r < len(sol) else "", mat[r] if r < len(mat) else ""]
            rows.append(row)
        return [_table(head, rows)]
    return []


def _blocks_stats(payload, result):
    levels = payload.get("levels", [])
    rows = []
    for i, lv in enumerate(result.get("levels", [])):
        nominal = levels[i].get("nominal", "") if i < len(levels) else ""
        rows.append([nominal or f"Nivel {i + 1}", lv.get("n", 0), _fmt(lv.get("mean")),
                     _fmt(lv.get("sd")), _fmt(lv.get("cv")), _fmt(lv.get("dev")),
                     lv.get("verdict", "—")])
    return [_table(["Nivel (nominal)", "n", "Promedio", "DE", "CV%", "%desv", "Dictamen"], rows)]


def _blocks_suitability(payload, result):
    run = (result.get("runs") or [{}])[0]
    return [_kv([("n", run.get("n", 0)), ("Promedio", _fmt(run.get("mean"))),
                 ("CV%", _fmt(run.get("cv"))), ("Dictamen", run.get("verdict", "—"))])]


def _blocks_curve(payload, result):
    out = []
    reg = result.get("regression")
    if reg:
        out.append(_kv([("Pendiente (b)", _fmt(reg.get("slope"))),
                        ("Ordenada (a)", _fmt(reg.get("intercept"))),
                        ("r", _fmt(reg.get("r"))), ("n", reg.get("n", 0)),
                        ("Dictamen (r)", "CUMPLE" if result.get("r_ok") else
                         ("—" if result.get("r_ok") is None else "NO CUMPLE"))]))
    levels = payload.get("levels", [])
    rows = []
    for i, p in enumerate(result.get("points", [])):
        nominal = levels[i].get("nominal", "") if i < len(levels) else ""
        rows.append([nominal or f"Nivel {i + 1}", _fmt(p.get("calc")),
                     _fmt(p.get("pct_quant")), _fmt(p.get("error")),
                     "CUMPLE" if p.get("ok") else ("—" if p.get("ok") is None else "NO CUMPLE")])
    if rows:
        out.append(_table(["Nivel nominal", "Conc. calc.", "% cuantif.", "% error", "Dictamen"], rows))
    return out


def _blocks_recovery(payload, result):
    levels = payload.get("levels", [])
    rows = []
    for i, lv in enumerate(result.get("levels", [])):
        label = levels[i].get("label") or levels[i].get("id") or f"Nivel {i + 1}" if i < len(levels) else f"Nivel {i + 1}"
        rows.append([label, _fmt(lv.get("recovery")) + " %"])
    o = result.get("overall", {})
    return [_table(["Nivel", "% Recobro"], rows),
            _kv([("Recobro promedio", _fmt(o.get("mean")) + " %"),
                 ("CV del recobro", _fmt(o.get("cv")) + " %"), ("Dictamen", o.get("verdict", "—"))])]


def _blocks_matrix(payload, result):
    rows = [[f"Lote {i + 1}", _fmt(lt.get("fmn"))] for i, lt in enumerate(result.get("lots", []))]
    o = result.get("overall", {})
    return [_table(["Lote", "FMN"], rows),
            _kv([("FMN promedio", _fmt(o.get("mean"))),
                 ("CV del FMN", _fmt(o.get("cv")) + " %"), ("Dictamen", o.get("verdict", "—"))])]


def _blocks_ratio(payload, result):
    rows = []
    for i, r in enumerate(result.get("rows", [])):
        rows.append([f"Lote {i + 1}", _fmt(r.get("analyte_pct")) + " %",
                     "CUMPLE" if r.get("ok_analyte") else ("—" if r.get("ok_analyte") is None else "NO CUMPLE"),
                     _fmt(r.get("is_pct")) + " %",
                     "CUMPLE" if r.get("ok_is") else ("—" if r.get("ok_is") is None else "NO CUMPLE")])
    return [_table(["Lote", "% analito", "Dictamen", "% EI", "Dictamen"], rows)]


def _blocks_free(payload, result):
    out = []
    tables = payload.get("tables", [])
    stats = result.get("tables", [])
    for ti, t in enumerate(tables):
        headers = t.get("headers", [])
        out.append(_table([t.get("title", f"Tabla {ti + 1}")] + headers,
                          [[str(r + 1)] + (row + [""] * len(headers))[:len(headers)]
                           for r, row in enumerate(t.get("rows", []))]))
        col_stats = stats[ti].get("stats", []) if ti < len(stats) else []
        srows = []
        for c, hd in enumerate(headers):
            s = col_stats[c] if c < len(col_stats) else {}
            if s.get("n"):
                srows.append([hd, s.get("n"), _fmt(s.get("mean")), _fmt(s.get("sd")), _fmt(s.get("cv"))])
        if srows:
            out.append(_table(["Columna", "n", "Promedio", "DE", "CV%"], srows))
    return out


_FORMATTERS = {
    "stats": _blocks_stats, "suitability": _blocks_suitability, "curve": _blocks_curve,
    "recovery": _blocks_recovery, "matrix": _blocks_matrix, "ratio": _blocks_ratio,
    "free": _blocks_free,
}


def build_report(project):
    records = {m.module: m for m in ModuleData.query.filter_by(project_id=project.id).all()}
    sections = []
    for mod in MODULES:
        record = records.get(mod.id)
        if record is None:
            continue
        payload = record.get_data()
        try:
            result = compute(mod.id, payload, project)
            result_blocks = _FORMATTERS[mod.kind](payload, result)
        except Exception:
            continue
        if mod.kind == "free":
            blocks = result_blocks
        else:
            blocks = []
            subtitle = payload.get("subtitle")
            if subtitle:
                blocks.append(_caption(subtitle))
            data_blocks = _data_blocks(mod.kind, payload, project.unit)
            if data_blocks:
                blocks.append(_caption("Datos capturados"))
                blocks += data_blocks
            if result_blocks:
                blocks.append(_caption("Resultados"))
                blocks += result_blocks
        if blocks:
            sections.append({"name": mod.name, "section": mod.section,
                             "updated_by": record.updated_by, "blocks": blocks})
    return {
        "molecule": project.molecule or "—",
        "code": project.code or "—",
        "unit": project.unit,
        "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "sections": sections,
    }


def render_pdf(project):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    data = build_report(project)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"Informe {data['code']}",
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    styles = getSampleStyleSheet()
    petrol = colors.HexColor("#0b3a48")
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=16, textColor=petrol, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    sec = ParagraphStyle("sec", parent=styles["Heading2"], fontSize=11.5, textColor=petrol,
                         spaceBefore=12, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5)
    cap = ParagraphStyle("cap", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#4a5b62"),
                         fontName="Helvetica-Bold", spaceBefore=4, spaceAfter=2)

    story = [Paragraph("Informe de validación bioanalítica", h1),
             Paragraph(f"Molécula: <b>{data['molecule']}</b> &nbsp;·&nbsp; Código: "
                       f"<b>{data['code']}</b> &nbsp;·&nbsp; Unidad: {data['unit']}", sub),
             Paragraph(f"Generado: {data['generated']}", sub), Spacer(1, 6)]

    if not data["sections"]:
        story.append(Paragraph("Esta hoja todavía no tiene módulos con datos guardados.", small))

    def make_table(head, rows):
        body = [head] + [[str(c) for c in r] for r in rows]
        t = Table(body, repeatRows=1, hAlign="LEFT")
        style = [("BACKGROUND", (0, 0), (-1, 0), petrol),
                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTSIZE", (0, 0), (-1, -1), 8),
                 ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                 ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9e2e6")),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f8")]),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        for ri, r in enumerate(body):
            for ci, c in enumerate(r):
                if c == "CUMPLE":
                    style.append(("TEXTCOLOR", (ci, ri), (ci, ri), colors.HexColor("#1f7a4d")))
                elif c == "NO CUMPLE":
                    style.append(("TEXTCOLOR", (ci, ri), (ci, ri), colors.HexColor("#b3261e")))
        t.setStyle(TableStyle(style))
        return t

    for s in data["sections"]:
        story.append(Paragraph(f"{s['section']} — {s['name']}", sec))
        for b in s["blocks"]:
            if b["type"] == "caption":
                story.append(Paragraph(b["text"], cap))
            elif b["type"] == "table" and b["rows"]:
                story.append(make_table(b["head"], b["rows"]))
                story.append(Spacer(1, 4))
            elif b["type"] == "kv":
                txt = " &nbsp;|&nbsp; ".join(f"{k}: <b>{v}</b>" for k, v in b["items"])
                story.append(Paragraph(txt, small))
                story.append(Spacer(1, 4))

    doc.build(story)
    buf.seek(0)
    return buf
