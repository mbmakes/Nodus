# -*- coding: utf-8 -*-
"""engcalc.py (dogrulanmis hesaplar) ve eng_calc aracinin entegrasyonu."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engcalc


def cell(md: str, label: str) -> float:
    m = re.search(r"\| \**" + re.escape(label) + r"[^|]*\| \**([-\d.,e+]+)", md)
    return float(m.group(1).replace(",", ""))


def test_pipe_pressure_drop_matches_hand_calc():
    md = engcalc.run("pipe_pressure_drop", {"diameter_mm": 50, "length_m": 100, "flow_lps": 5})
    assert cell(md, "Basınç kaybı ΔP") == pytest.approx(110.9, rel=0.01)   # f=0.01713, V=2.546 m/s
    assert cell(md, "Reynolds sayısı Re") == pytest.approx(126893, rel=0.01)
    laminar = engcalc.run("pipe_pressure_drop", {"diameter_mm": 10, "length_m": 1, "velocity_ms": 0.1})
    assert "laminer" in laminar and cell(laminar, "Sürtünme katsayısı f") == pytest.approx(64 / cell(laminar, "Reynolds sayısı Re"), rel=0.01)


def test_beam_deflection_cases():
    md = engcalc.run("beam_deflection", {"length_m": 2, "load_n": 500, "b_mm": 40, "h_mm": 40})
    assert cell(md, "Maksimum sehim δ") == pytest.approx(29.76, rel=0.005)
    assert cell(md, "Maksimum eğilme gerilmesi σ") == pytest.approx(93.75, rel=0.005)
    ss = engcalc.run("beam_deflection", {"support": "simply_supported", "load": "udl", "length_m": 3, "w_n_per_m": 1000, "section": "circle", "d_mm": 50})
    assert cell(ss, "Maksimum moment M") == pytest.approx(1000 * 9 / 8)


def test_steam_table():
    md = engcalc.run("steam_table", {"p_min_bar": 1, "p_max_bar": 2, "n": 2})
    assert "| 1.000 | 99.61 |" in md and "| 2.000 | 120.21 |" in md


def test_pump_shaft_bolt_wall_hand_calcs():
    p = engcalc.run("pump_power", {"flow_lps": 10, "head_m": 30, "efficiency": 0.7})
    assert cell(p, "Mil gücü") == pytest.approx(1000 * 9.80665 * 0.01 * 30 / 0.7 / 1000, rel=0.002)   # 4.203 kW
    s = engcalc.run("shaft_torsion", {"power_kw": 15, "rpm": 1450, "d_mm": 40, "length_m": 0.5})
    assert cell(s, "Tork T") == pytest.approx(98.79, rel=0.002)
    assert cell(s, "Maksimum kayma gerilmesi τ") == pytest.approx(16 * 98.79 / (3.14159265 * 0.04 ** 3) / 1e6, rel=0.002)   # 7.86 MPa
    b = engcalc.run("bolt_check", {"size": "M12", "grade": "8.8", "axial_n": 20000})
    assert cell(b, "Cıvata başına çekme σ") == pytest.approx(20000 / 84.3, rel=0.002)
    assert cell(b, "Güvenlik katsayısı") == pytest.approx(600 / (20000 / 84.3), rel=0.01)
    w = engcalc.run("wall_heat", {"layers": [{"thickness_mm": 200, "k_wm": 0.8}], "t_in_c": 20, "t_out_c": -5})
    assert cell(w, "Toplam direnç") == pytest.approx(0.1 + 0.25 + 0.04)
    assert cell(w, "Isı akısı q") == pytest.approx(25 / 0.39, rel=0.002)


@pytest.mark.parametrize("calc,params", [
    ("pump_power", {"flow_lps": 5, "head_m": 10, "efficiency": 1.5}),
    ("shaft_torsion", {"d_mm": 30}),
    ("bolt_check", {"size": "M99", "axial_n": 1}),
    ("bolt_check", {"size": "M10"}),
    ("wall_heat", {"layers": [], "t_in_c": 20, "t_out_c": 0}),
    ("pipe_pressure_drop", {"diameter_mm": -5, "length_m": 10, "flow_lps": 1}),
    ("pipe_pressure_drop", {"diameter_mm": 50, "length_m": 10}),
    ("beam_deflection", {"length_m": 2, "load_n": 500, "section": "hollow_square", "b_mm": 10, "t_mm": 6}),
    ("beam_deflection", {"support": "x", "length_m": 1, "load_n": 1}),
    ("steam_table", {"p_min_bar": 5, "p_max_bar": 1}),
    ("yok_hesap", {}),
])
def test_bad_input_is_rejected(calc, params):
    with pytest.raises(ValueError):
        engcalc.run(calc, params)


def test_tool_dispatch_and_policy():
    from agent_core import NodusAgent
    from orchestrator import is_safe_action
    from tools import ERR
    agent = NodusAgent()
    ok = agent.execute_action({"action": "eng_calc", "params": {"calc": "steam_table", "p_min_bar": 1, "p_max_bar": 1, "n": 1}})
    assert ok["success"] and "99.61" in ok["output"]
    bad = agent.execute_action({"action": "eng_calc", "params": {"calc": "pipe_pressure_drop", "diameter_mm": 0}})
    assert not bad["success"] and bad["output"].startswith(ERR)
    assert is_safe_action({"action": "eng_calc"})[0]   # saf hesap: onay istemez
