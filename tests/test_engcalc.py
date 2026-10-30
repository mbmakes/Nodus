# -*- coding: utf-8 -*-
"""engcalc.py (dogrulanmis hesaplar) ve eng_calc aracinin entegrasyonu."""
import math
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


def test_pipe_warns_when_fluid_is_not_liquid():
    water = engcalc.run("pipe_pressure_drop", {"diameter_mm": 50, "length_m": 100, "flow_lps": 5})
    assert "Uyarı" not in water                                          # 20 C'de sivi: uyari yok
    steam = engcalc.run("pipe_pressure_drop", {"diameter_mm": 50, "length_m": 100, "flow_lps": 5, "temperature_c": 120})
    assert "gaz fazında" in steam                                        # 1 bar'da 120 C 'su' buhardir; eskiden sessizce hesaplaniyordu
    assert "GEÇERSİZ" in engcalc.run("pipe_pressure_drop", {"diameter_mm": 10, "length_m": 500, "velocity_ms": 30, "fluid": "Air"})


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


def test_exchanger_buckling_orifice_bearing_psychro_npsh_hand_calcs():
    hx = engcalc.run("heat_exchanger", {"t_hot_in": 100, "t_hot_out": 60, "t_cold_in": 20, "t_cold_out": 40, "q_kw": 10, "u_wm2k": 500})
    assert cell(hx, "LMTD") == pytest.approx(20 / math.log(1.5), rel=0.001)
    assert cell(hx, "Gerekli alan A") == pytest.approx(10000 / (500 * 20 / math.log(1.5)), rel=0.002)
    col = engcalc.run("column_buckling", {"length_m": 0.5, "section": "rect", "b_mm": 20, "h_mm": 20, "load_n": 50000})
    assert cell(col, "Kritik burkulma yükü Pcr") == pytest.approx(math.pi ** 2 * 210e9 * (20 * 20 ** 3 / 12 * 1e-12) / 0.25 / 1000, rel=0.002)
    assert "Euler formülü geçersiz" in col                              # sigma_cr 276 MPa > akma 250 MPa
    ori = engcalc.run("orifice_flow", {"pipe_d_mm": 100, "orifice_d_mm": 50, "dp_kpa": 10})
    assert cell(ori, "Debi Q") == pytest.approx(0.61 * math.pi * 0.05 ** 2 / 4 * math.sqrt(2 * 10000 / 1000) / math.sqrt(1 - 0.5 ** 4) * 1000, rel=0.002)
    assert cell(engcalc.run("bearing_life", {"c_kn": 30, "p_kn": 5, "rpm": 1500}), "L10h") == pytest.approx(2400)
    assert cell(engcalc.run("psychrometrics", {"t_c": 25, "rh_percent": 50}), "Çiğ noktası") == pytest.approx(13.9, abs=0.1)
    npsh = engcalc.run("npsh_available", {"temperature_c": 20, "static_head_m": 2, "loss_m": 1.5})
    assert cell(npsh, "NPSH mevcut") == pytest.approx((101325 - 2339) / (998.2 * 9.80665) + 0.5, rel=0.002)
    assert "kavitasyon" in engcalc.run("npsh_available", {"temperature_c": 20, "npsh_required_m": 10.5})


def test_pressure_vessel_and_fatigue_hand_calcs():
    pv = engcalc.run("pressure_vessel", {"pressure_mpa": 2, "inner_d_mm": 500, "thickness_mm": 5})
    assert cell(pv, "Çevresel gerilme") == pytest.approx(2 * 500 / (2 * 5)) and cell(pv, "Eksenel gerilme") == pytest.approx(2 * 500 / (4 * 5))
    assert cell(pv, "Von Mises") == pytest.approx(math.sqrt(3) / 2 * 100, rel=0.001)
    assert cell(engcalc.run("pressure_vessel", {"pressure_mpa": 2, "inner_d_mm": 500, "thickness_mm": 5, "shape": "sphere"}), "Gerilme σ") == pytest.approx(50)
    ft = engcalc.run("fatigue_goodman", {"sigma_max_mpa": 200, "sigma_min_mpa": 0, "ult_mpa": 500, "endurance_mpa": 200})
    assert cell(ft, "Yorulma güvenlik katsayısı") == pytest.approx(1 / (100 / 200 + 100 / 500), rel=0.002)
    assert "Uyarı" in engcalc.run("fatigue_goodman", {"sigma_max_mpa": 400, "sigma_min_mpa": 0, "ult_mpa": 500, "endurance_mpa": 200, "yield_mpa": 350})


@pytest.mark.parametrize("calc,params", [
    ("pressure_vessel", {"pressure_mpa": 2, "inner_d_mm": 100, "thickness_mm": 20}),                      # D/t < 20: kalin cidar
    ("fatigue_goodman", {"sigma_max_mpa": 10, "sigma_min_mpa": 50, "ult_mpa": 500, "endurance_mpa": 200}),
    ("heat_exchanger", {"t_hot_in": 50, "t_hot_out": 40, "t_cold_in": 60, "t_cold_out": 70, "q_kw": 1}),   # sicak taraf soguktan soguk
    ("column_buckling", {"length_m": 1, "end": "x", "b_mm": 10, "h_mm": 10}),
    ("orifice_flow", {"pipe_d_mm": 100, "orifice_d_mm": 95, "dp_kpa": 10}),                                # beta > 0.75
    ("bearing_life", {"c_kn": 1, "p_kn": 1, "rpm": 100, "type": "x"}),
    ("psychrometrics", {"t_c": 20, "rh_percent": 150}),
])
def test_new_calcs_reject_bad_input(calc, params):
    with pytest.raises(ValueError):
        engcalc.run(calc, params)


@pytest.mark.parametrize("calc,params", [
    ("pump_power", {"flow_lps": 5, "head_m": 10, "efficiency": 1.5}),
    ("shaft_torsion", {"d_mm": 30}),
    ("bolt_check", {"size": "M99", "axial_n": 1}),
    ("bolt_check", {"size": "M10"}),
    ("wall_heat", {"layers": [], "t_in_c": 20, "t_out_c": 0}),
    ("wall_heat", {"layers": ["beton"], "t_in_c": 20, "t_out_c": 0}),   # nesne degil: eskiden AttributeError sizardi
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
