"""
Motor de cálculo bioanalítico — idéntico a las hojas del libro de Excel original.

Todas las fórmulas conservan precisión completa (float de 64 bits). El redondeo es
únicamente de presentación y se decide en la capa de interfaz, no aquí.

Equivalencias verificadas contra el libro `Machote_en_NG.xlsm`:
  - CV%   = DESVEST / PROMEDIO * 100           (DESVEST muestral, n-1)
  - %desv = 100 * (nominal - promedio) / nominal
  - %Recobro = promedio_matriz * 100 / promedio_solucion
  - FMN   = (analito/EI)_matriz / (analito/EI)_solucion
  - %acarreo = area_blanco * 100 / area_referencia
  - Curva: conc = (respuesta - a) / b ; %error = |100 - %cuantificado|
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence


# --------------------------------------------------------------------------- #
# Utilidades numéricas (toleran coma decimal y celdas vacías, como el Excel)
# --------------------------------------------------------------------------- #
def num(value) -> float:
    """Convierte a float aceptando coma decimal y espacios. Vacío/None -> NaN."""
    if value is None:
        return math.nan
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", ".")
    if s == "":
        return math.nan
    try:
        return float(s)
    except ValueError:
        return math.nan


def clean(values: Iterable) -> list[float]:
    """Lista de números válidos (descarta vacíos y no numéricos)."""
    return [x for x in (num(v) for v in values) if not math.isnan(x)]


# --------------------------------------------------------------------------- #
# Estadística base
# --------------------------------------------------------------------------- #
def count(values: Iterable) -> int:
    return len(clean(values))


def mean(values: Iterable) -> float:
    data = clean(values)
    return sum(data) / len(data) if data else math.nan


def stdev(values: Iterable) -> float:
    """Desviación estándar MUESTRAL (n-1), igual que DESVEST de Excel."""
    data = clean(values)
    n = len(data)
    if n < 2:
        return math.nan
    m = sum(data) / n
    var = sum((x - m) ** 2 for x in data) / (n - 1)
    return math.sqrt(var)


def cv(values: Iterable) -> float:
    """Coeficiente de variación en % = DESVEST / PROMEDIO * 100."""
    m = mean(values)
    if math.isnan(m) or m == 0:
        return math.nan
    return stdev(values) / m * 100.0


def pct_dev(nominal, observed_mean) -> float:
    """% de desviación respecto al valor nominal = 100 * (nominal - prom) / nominal."""
    nominal = num(nominal)
    if math.isnan(nominal) or nominal == 0 or math.isnan(observed_mean):
        return math.nan
    return 100.0 * (nominal - observed_mean) / nominal


# --------------------------------------------------------------------------- #
# Regresión lineal ponderada  y = a + b·x
# --------------------------------------------------------------------------- #
_WEIGHTS = ("1", "1/x", "1/x2", "1/y", "1/y2")


def _weight(kind: str, x: float, y: float) -> float:
    if kind == "1/x":
        return 1.0 / abs(x) if x != 0 else 0.0
    if kind == "1/x2":
        return 1.0 / (x * x) if x != 0 else 0.0
    if kind == "1/y":
        return 1.0 / abs(y) if y != 0 else 0.0
    if kind == "1/y2":
        return 1.0 / (y * y) if y != 0 else 0.0
    return 1.0  # peso unitario (mínimos cuadrados ordinarios)


def weighted_regression(xs: Sequence, ys: Sequence, weight: str = "1") -> Optional[dict]:
    """
    Ajuste por mínimos cuadrados ponderados. Devuelve pendiente, ordenada,
    coeficiente de correlación (r), r² y n; o None si no hay puntos suficientes.
    """
    pts = []
    for xv, yv in zip(xs, ys):
        x, y = num(xv), num(yv)
        if not math.isnan(x) and not math.isnan(y):
            pts.append((x, y))
    if len(pts) < 2:
        return None

    sw = swx = swy = swxx = swxy = swyy = 0.0
    for x, y in pts:
        w = _weight(weight, x, y)
        sw += w
        swx += w * x
        swy += w * y
        swxx += w * x * x
        swxy += w * x * y
        swyy += w * y * y

    denom = sw * swxx - swx * swx
    if denom == 0:
        return None
    slope = (sw * swxy - swx * swy) / denom
    intercept = (swy - slope * swx) / sw

    # coeficiente de correlación ponderado
    cov = sw * swxy - swx * swy
    vx = sw * swxx - swx * swx
    vy = sw * swyy - swy * swy
    r = cov / math.sqrt(vx * vy) if vx > 0 and vy > 0 else math.nan

    return {
        "slope": slope,
        "intercept": intercept,
        "r": r,
        "r2": (r * r) if not math.isnan(r) else math.nan,
        "n": len(pts),
        "weight": weight,
    }


def back_calc(response, slope: float, intercept: float) -> float:
    """Concentración calculada a partir de la respuesta: x = (y - a) / b."""
    y = num(response)
    if math.isnan(y) or slope == 0:
        return math.nan
    return (y - intercept) / slope


# --------------------------------------------------------------------------- #
# Bloques de criterio (dictamen CUMPLE / NO CUMPLE)
# --------------------------------------------------------------------------- #
def column_stats(values: Sequence, nominal=None, *, cv_limit=15.0,
                 dev_limit=15.0) -> dict:
    """Estadísticos de una columna (un nivel) con su dictamen."""
    n = count(values)
    m = mean(values)
    sd = stdev(values)
    cvv = cv(values)
    dev = pct_dev(nominal, m) if nominal is not None else math.nan

    ok_cv = (cvv <= cv_limit + 1e-9) if (n >= 2 and not math.isnan(cvv)) else None
    ok_dev = (abs(dev) <= dev_limit + 1e-9) if not math.isnan(dev) else None
    verdict = _verdict(n, ok_cv, ok_dev)

    return {
        "n": n, "mean": m, "sd": sd, "cv": cvv, "dev": dev,
        "ok_cv": ok_cv, "ok_dev": ok_dev,
        "cv_limit": cv_limit, "dev_limit": dev_limit, "verdict": verdict,
    }


def _verdict(n: int, *flags) -> str:
    present = [f for f in flags if f is not None]
    if n == 0 or not present:
        return "—"
    if n < 2:
        return "n insuficiente"
    return "CUMPLE" if all(present) else "NO CUMPLE"


# --------------------------------------------------------------------------- #
# Cálculos específicos por módulo de validación
# --------------------------------------------------------------------------- #
def system_suitability(area_ratios: Sequence, *, cv_limit=2.0) -> dict:
    """Aptitud del sistema: CV% de la relación de áreas de las inyecciones."""
    n = count(area_ratios)
    cvv = cv(area_ratios)
    ok = (cvv <= cv_limit + 1e-9) if (n >= 2 and not math.isnan(cvv)) else None
    return {
        "n": n, "mean": mean(area_ratios), "cv": cvv,
        "cv_limit": cv_limit,
        "verdict": "—" if ok is None else ("CUMPLE" if ok else "NO CUMPLE"),
    }


def recovery(solution_reps: Sequence, matrix_reps: Sequence) -> dict:
    """%Recobro por nivel = promedio_matriz * 100 / promedio_solucion."""
    psol = mean(solution_reps)
    pmat = mean(matrix_reps)
    rec = (pmat * 100.0 / psol) if (not math.isnan(psol) and psol != 0) else math.nan
    return {"mean_solution": psol, "mean_matrix": pmat, "recovery": rec}


def recovery_overall(level_recoveries: Sequence, *, cv_limit=15.0) -> dict:
    """Promedio y CV% del recobro entre niveles."""
    m = mean(level_recoveries)
    cvv = cv(level_recoveries)
    ok = (cvv <= cv_limit + 1e-9) if (count(level_recoveries) >= 2 and not math.isnan(cvv)) else None
    return {
        "mean": m, "cv": cvv, "cv_limit": cv_limit,
        "verdict": "—" if ok is None else ("CUMPLE" if ok else "NO CUMPLE"),
    }


def matrix_factor(analyte_area, is_area, ref_analyte_area, ref_is_area) -> float:
    """Factor de Matriz Normalizado (FMN) de un lote."""
    a, i = num(analyte_area), num(is_area)
    ra, ri = num(ref_analyte_area), num(ref_is_area)
    if math.isnan(a) or math.isnan(i) or i == 0:
        return math.nan
    if math.isnan(ra) or math.isnan(ri) or ri == 0:
        return math.nan
    ratio_matrix = a / i
    ratio_solution = ra / ri
    if ratio_solution == 0:
        return math.nan
    return ratio_matrix / ratio_solution


def matrix_effect(fmn_values: Sequence, *, cv_limit=15.0) -> dict:
    """Promedio y CV% del FMN entre lotes."""
    m = mean(fmn_values)
    cvv = cv(fmn_values)
    ok = (cvv <= cv_limit + 1e-9) if (count(fmn_values) >= 2 and not math.isnan(cvv)) else None
    return {
        "mean": m, "cv": cvv, "cv_limit": cv_limit,
        "verdict": "—" if ok is None else ("CUMPLE" if ok else "NO CUMPLE"),
    }


def carryover(blank_area, reference_area) -> float:
    """% de acarreo / selectividad = area_blanco * 100 / area_referencia."""
    b, ref = num(blank_area), num(reference_area)
    if math.isnan(b) or math.isnan(ref) or ref == 0:
        return math.nan
    return b * 100.0 / ref


def calibration_point(nominal, response, slope, intercept) -> dict:
    """Por nivel de la curva: concentración calculada, % cuantificado y % error."""
    nom = num(nominal)
    calc = back_calc(response, slope, intercept)
    if math.isnan(calc) or math.isnan(nom) or nom == 0:
        pct_q = math.nan
        err = math.nan
    else:
        pct_q = calc / nom * 100.0
        err = abs(100.0 - pct_q)
    return {"nominal": nom, "calc": calc, "pct_quant": pct_q, "error": err}
