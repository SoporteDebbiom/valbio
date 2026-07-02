"""Pruebas del motor de cálculo: verifican paridad con el libro de Excel."""
import math

import pytest

from app.validation import calculations as calc


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


# --- estadística base ------------------------------------------------------- #
def test_mean_stdev_cv_match_excel():
    data = [5, 5, 5, 5, 6, 5]
    assert approx(calc.mean(data), 5.1666666667)
    assert approx(calc.stdev(data), 0.4082482905)   # DESVEST muestral
    assert approx(calc.cv(data), 7.9015797148)


def test_num_accepts_comma_and_blanks():
    assert calc.num("1,5") == 1.5
    assert math.isnan(calc.num(""))
    assert math.isnan(calc.num(None))
    assert calc.count(["1", "", "2", None, "x"]) == 2


def test_stdev_needs_two_points():
    assert math.isnan(calc.stdev([3]))
    assert math.isnan(calc.cv([]))


def test_pct_dev():
    assert approx(calc.pct_dev(100, 95), 5.0)
    assert approx(calc.pct_dev(100, 110), -10.0)
    assert math.isnan(calc.pct_dev(0, 5))


# --- regresión -------------------------------------------------------------- #
def test_regression_perfect_line():
    xs = [1, 2, 3, 4, 5]
    ys = [3, 5, 7, 9, 11]          # y = 2x + 1
    reg = calc.weighted_regression(xs, ys, "1")
    assert approx(reg["slope"], 2.0)
    assert approx(reg["intercept"], 1.0)
    assert approx(reg["r"], 1.0)


def test_regression_weighted_runs():
    xs = [10, 50, 100, 200, 400]
    ys = [21, 101, 201, 401, 801]  # y = 2x + 1
    for w in ("1", "1/x", "1/x2", "1/y", "1/y2"):
        reg = calc.weighted_regression(xs, ys, w)
        assert reg is not None
        assert approx(reg["slope"], 2.0, 1e-3)


def test_back_calc_and_point():
    pt = calc.calibration_point(nominal=100, response=201, slope=2.0, intercept=1.0)
    assert approx(pt["calc"], 100.0)
    assert approx(pt["pct_quant"], 100.0)
    assert approx(pt["error"], 0.0)


# --- módulos ---------------------------------------------------------------- #
def test_recovery():
    r = calc.recovery([100, 100, 100], [80, 80, 80])
    assert approx(r["recovery"], 80.0)


def test_matrix_factor():
    # (1100/500)/(1000/500) = 2.2/2.0 = 1.1
    assert approx(calc.matrix_factor(1100, 500, 1000, 500), 1.1)


def test_carryover():
    assert approx(calc.carryover(10, 100), 10.0)
    assert math.isnan(calc.carryover(10, 0))


def test_column_stats_verdict():
    s = calc.column_stats([100, 102, 98, 101, 99], nominal=100, cv_limit=15, dev_limit=15)
    assert s["n"] == 5
    assert s["verdict"] == "CUMPLE"
    bad = calc.column_stats([100, 140, 60], nominal=100, cv_limit=15, dev_limit=15)
    assert bad["verdict"] == "NO CUMPLE"


def test_system_suitability():
    s = calc.system_suitability([1.0, 1.0, 1.0, 1.0, 1.01, 1.0], cv_limit=2)
    assert s["verdict"] == "CUMPLE"


def test_no_exceptions_on_empty():
    # nunca debe lanzar excepción ante datos vacíos
    assert math.isnan(calc.cv([]))
    assert calc.weighted_regression([], []) is None
    assert math.isnan(calc.carryover("", ""))
