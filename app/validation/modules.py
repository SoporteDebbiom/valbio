"""Catálogo de módulos de validación y despacho de cálculo del lado del servidor.

Cada módulo declara su metadato (id, sección, nombre, descripción) y una función
`compute(payload, project)` que recibe la captura del cliente y devuelve los
resultados ya calculados con el motor. Toda la lógica numérica vive en
`calculations.py`; aquí sólo se orquesta. Añadir un módulo nuevo = añadir una
entrada y una función de cálculo (sin tocar plantillas ni rutas).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from app.validation import calculations as calc


@dataclass(frozen=True)
class Module:
    id: str
    section: str
    name: str
    description: str
    kind: str  # 'stats' | 'suitability' | 'curve' | 'recovery' | 'matrix' | 'ratio'


MODULES: list[Module] = [
    Module("aptitud", "Idoneidad", "Aptitud del Sistema",
           "CV de la relación de áreas por corrida analítica.", "suitability"),
    Module("curva", "Curva y exactitud", "Curva de Calibración",
           "Regresión ponderada, pendiente, r y % de error.", "curve"),
    Module("preexa", "Curva y exactitud", "Precisión y Exactitud",
           "Repetibilidad y reproducibilidad por nivel.", "stats"),
    Module("segcc", "Curva y exactitud", "Seguimiento de CC",
           "Control de curvas y CC entre corridas.", "stats"),
    Module("estsol", "Estabilidad", "Estabilidad de la Solución",
           "Estabilidad de soluciones de referencia.", "stats"),
    Module("estmues", "Estabilidad", "Estabilidad de la Muestra",
           "Corto y largo plazo en matriz.", "stats"),
    Module("estmuepro", "Estabilidad", "Estabilidad Muestra Procesada",
           "Estabilidad de la muestra ya procesada.", "stats"),
    Module("estaut", "Estabilidad", "Estabilidad en Automuestreador",
           "Estabilidad en el automuestreador.", "stats"),
    Module("ccd", "Estabilidad", "Ciclos Congelación-Descongelación",
           "Estabilidad tras ciclos C/D.", "stats"),
    Module("selec", "Selectividad e interferencias", "Selectividad",
           "Respuesta en blanco respecto a la referencia.", "ratio"),
    Module("interf", "Selectividad e interferencias", "Interferencias",
           "Sustancias concomitantes por nivel.", "stats"),
    Module("matriz", "Recuperación", "Efecto Matriz",
           "Factor de Matriz Normalizado (FMN).", "matrix"),
    Module("acarreo", "Recuperación", "Acarreo",
           "Carryover de analito y EI respecto a la referencia.", "ratio"),
    Module("recobro", "Recuperación", "Recobro",
           "% de recobro de analito/EI por nivel.", "recovery"),
    Module("tabla", "Tablas personalizadas", "Tabla Personalizada",
           "Crea tus propias tablas: agrega tablas, filas y columnas, y escribe libremente.",
           "free"),
]

MODULE_BY_ID = {m.id: m for m in MODULES}


def sections() -> dict[str, list[Module]]:
    out: dict[str, list[Module]] = {}
    for m in MODULES:
        out.setdefault(m.section, []).append(m)
    return out


# --------------------------------------------------------------------------- #
# Cálculo por tipo de módulo
# --------------------------------------------------------------------------- #
def _f(x):
    """JSON no admite NaN/Infinity: se serializa como None y la UI muestra '—'."""
    return None if (x is None or (isinstance(x, float) and not math.isfinite(x))) else x


def _clean_stats(d: dict) -> dict:
    return {k: _f(v) for k, v in d.items()}


def compute(module_id: str, payload: dict, project) -> dict:
    mod = MODULE_BY_ID.get(module_id)
    if mod is None:
        return {"error": "Módulo desconocido"}
    handler: Callable = _HANDLERS[mod.kind]
    return handler(payload, project)


def _compute_stats(payload: dict, project) -> dict:
    """Matriz niveles × réplicas con dictamen por nivel.

    payload = {
      "limits": {"cv": 15, "dev": 15, "cv_lic": 20, "dev_lic": 20},
      "levels": [
         {"nominal": "100", "lic": false, "replicates": ["100","102",...]},
         ...
      ]
    }
    """
    limits = payload.get("limits", {})
    results = []
    for level in payload.get("levels", []):
        is_lic = bool(level.get("lic"))
        cv_lim = limits.get("cv_lic" if is_lic else "cv", 20 if is_lic else 15)
        dev_lim = limits.get("dev_lic" if is_lic else "dev", 20 if is_lic else 15)
        stats = calc.column_stats(
            level.get("replicates", []),
            nominal=level.get("nominal"),
            cv_limit=float(cv_lim), dev_limit=float(dev_lim),
        )
        results.append(_clean_stats(stats))
    return {"levels": results}


def _compute_suitability(payload: dict, project) -> dict:
    cv_lim = float(payload.get("cv_limit", 2))
    runs = []
    for run in payload.get("runs", []):
        ratios = []
        for inj in run.get("injections", []):
            a, ei = calc.num(inj.get("analyte")), calc.num(inj.get("is"))
            ratios.append(a / ei if (not math.isnan(a) and not math.isnan(ei) and ei != 0) else "")
        runs.append({"ratios": [_f(r if r != "" else None) for r in ratios],
                     **_clean_stats(calc.system_suitability(ratios, cv_limit=cv_lim))})
    return {"runs": runs}


def _compute_curve(payload: dict, project) -> dict:
    weight = payload.get("weight", "1")
    xs = [lvl.get("nominal") for lvl in payload.get("levels", [])]
    ys = [lvl.get("response") for lvl in payload.get("levels", [])]
    reg = calc.weighted_regression(xs, ys, weight)
    limits = payload.get("limits", {})
    err_lim = float(limits.get("error", 15))

    points = []
    if reg:
        for lvl in payload.get("levels", []):
            pt = calc.calibration_point(lvl.get("nominal"), lvl.get("response"),
                                        reg["slope"], reg["intercept"])
            err = pt["error"]
            ok = (err <= err_lim + 1e-9) if not math.isnan(err) else None
            points.append({**{k: _f(v) for k, v in pt.items()},
                           "ok": ok})
    reg_out = {k: _f(v) for k, v in reg.items()} if reg else None
    r_ok = (reg["r"] >= float(limits.get("r", 0.99)) - 1e-9) if reg and not math.isnan(reg["r"]) else None
    return {"regression": reg_out, "points": points, "r_ok": r_ok}


def _compute_recovery(payload: dict, project) -> dict:
    limits = payload.get("limits", {})
    levels = []
    recoveries = []
    for lvl in payload.get("levels", []):
        r = calc.recovery(lvl.get("solution", []), lvl.get("matrix", []))
        recoveries.append(r["recovery"])
        levels.append({k: _f(v) for k, v in r.items()})
    overall = calc.recovery_overall(recoveries, cv_limit=float(limits.get("cv", 15)))
    return {"levels": levels, "overall": _clean_stats(overall)}


def _compute_matrix(payload: dict, project) -> dict:
    ref = payload.get("reference", {})
    limits = payload.get("limits", {})
    fmns = []
    lots = []
    for lot in payload.get("lots", []):
        fmn = calc.matrix_factor(lot.get("analyte"), lot.get("is"),
                                 ref.get("analyte"), ref.get("is"))
        fmns.append(fmn)
        lots.append({"fmn": _f(fmn)})
    overall = calc.matrix_effect(fmns, cv_limit=float(limits.get("cv", 15)))
    return {"lots": lots, "overall": _clean_stats(overall)}


def _compute_ratio(payload: dict, project) -> dict:
    """Acarreo / Selectividad: % de respuesta del blanco respecto a la referencia."""
    limits = payload.get("limits", {})
    a_lim = float(limits.get("analyte", 20))
    ei_lim = float(limits.get("is", 5))
    rows = []
    for row in payload.get("rows", []):
        pa = calc.carryover(row.get("blank_analyte"), row.get("ref_analyte"))
        pe = calc.carryover(row.get("blank_is"), row.get("ref_is"))
        ok_a = (pa <= a_lim + 1e-9) if not math.isnan(pa) else None
        ok_e = (pe <= ei_lim + 1e-9) if not math.isnan(pe) else None
        rows.append({"analyte_pct": _f(pa), "is_pct": _f(pe),
                     "ok_analyte": ok_a, "ok_is": ok_e})
    return {"rows": rows, "analyte_limit": a_lim, "is_limit": ei_lim}


def _compute_free(payload: dict, project) -> dict:
    """Tablas libres: por cada columna numérica devuelve n, promedio, DE y CV%."""
    tables = []
    for table in payload.get("tables", []):
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        stats = []
        for c in range(len(headers)):
            column = [row[c] for row in rows if c < len(row)]
            n = calc.count(column)
            if n >= 1:
                sd = calc.stdev(column) if n >= 2 else float("nan")
                cvv = calc.cv(column) if n >= 2 else float("nan")
                stats.append({"n": n, "mean": _f(calc.mean(column)),
                              "sd": _f(sd), "cv": _f(cvv)})
            else:
                stats.append({"n": 0, "mean": None, "sd": None, "cv": None})
        tables.append({"stats": stats})
    return {"tables": tables}


_HANDLERS: dict[str, Callable] = {
    "stats": _compute_stats,
    "suitability": _compute_suitability,
    "curve": _compute_curve,
    "recovery": _compute_recovery,
    "matrix": _compute_matrix,
    "ratio": _compute_ratio,
    "free": _compute_free,
}
