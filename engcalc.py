# -*- coding: utf-8 -*-
"""Dogrulanmis muhendislik hesaplari. Model formulu elle yazmak yerine eng_calc ile bunlari cagirir.
Hesaplar saf fonksiyondur (yan etkisi yok), bu yuzden onay istemez. Cikti, birimleriyle Markdown'dir."""
import math

G = 9.80665


def _num(params: dict, key: str, default=None, positive=True) -> float:
    v = params.get(key, default)
    if v is None:
        raise ValueError(f"'{key}' parametresi gerekli.")
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' sayi olmali (gelen: {v!r}).")
    if not math.isfinite(v) or (positive and v <= 0):
        raise ValueError(f"'{key}' pozitif ve sonlu olmali (gelen: {v}).")
    return v


def _fluid_props(fluid: str, t_c: float, p_pa: float):
    """(yogunluk kg/m3, dinamik viskozite Pa.s). Akiskan CoolProp'ta yoksa hata verir."""
    from CoolProp.CoolProp import PropsSI
    T = t_c + 273.15
    return PropsSI("D", "T", T, "P", p_pa, fluid), PropsSI("V", "T", T, "P", p_pa, fluid)


def _friction(re: float, rel_rough: float) -> float:
    if re < 2300:
        return 64.0 / re
    f = 0.25 / math.log10(rel_rough / 3.7 + 5.74 / re ** 0.9) ** 2   # Swamee-Jain baslangic
    for _ in range(50):   # Colebrook-White
        new = (-2.0 * math.log10(rel_rough / 3.7 + 2.51 / (re * math.sqrt(f)))) ** -2
        if abs(new - f) < 1e-12:
            break
        f = new
    return f


def pipe_pressure_drop(params: dict) -> str:
    """Duz borudaki basinc kaybi (Darcy-Weisbach + Colebrook-White).
    params: diameter_mm, length_m, flow_lps | velocity_ms, fluid='Water', temperature_c=20, pressure_bar=1.01325, roughness_mm=0 (puruzsuz)"""
    d = _num(params, "diameter_mm") / 1000
    L = _num(params, "length_m")
    eps = _num(params, "roughness_mm", 0.0, positive=False) / 1000
    if eps < 0:
        raise ValueError("'roughness_mm' negatif olamaz.")
    area = math.pi * d * d / 4
    if "flow_lps" in params:
        q = _num(params, "flow_lps") / 1000
        v = q / area
    else:
        v = _num(params, "velocity_ms")
        q = v * area
    fluid = str(params.get("fluid", "Water"))
    t_c = _num(params, "temperature_c", 20, positive=False)
    p_pa = _num(params, "pressure_bar", 1.01325) * 1e5
    rho, mu = _fluid_props(fluid, t_c, p_pa)
    re = rho * v * d / mu
    f = _friction(re, eps / d)
    dp = f * (L / d) * rho * v * v / 2
    h = dp / (rho * G)
    regime = "laminer" if re < 2300 else "geçiş bölgesi (sonuç belirsiz)" if re < 4000 else "türbülanslı"
    return (f"**Borudaki basınç kaybı** (Darcy-Weisbach, Colebrook-White)\n\n"
            f"| Büyüklük | Değer | Birim |\n|---|---:|---|\n"
            f"| Akışkan | {fluid}, {t_c:g} °C, {p_pa / 1e5:.3f} bar | |\n"
            f"| Yoğunluk ρ | {rho:.1f} | kg/m³ |\n| Dinamik viskozite μ | {mu:.4e} | Pa·s |\n"
            f"| Çap D | {d * 1000:g} | mm |\n| Uzunluk L | {L:g} | m |\n| Pürüzlülük ε | {eps * 1000:g} | mm |\n"
            f"| Debi Q | {q * 1000:.4g} | L/s |\n| Ortalama hız V | {v:.4f} | m/s |\n"
            f"| Reynolds sayısı Re | {re:,.0f} ({regime}) | - |\n| Sürtünme katsayısı f | {f:.5f} | - |\n"
            f"| **Basınç kaybı ΔP** | **{dp / 1000:.3f}** | kPa |\n| Yük kaybı h | {h:.3f} | m |\n\n"
            f"ΔP = f · (L/D) · ρV²/2")


_BEAMS = {
    # (mesnet, yuk): (sehim, moment, sehim formulu, moment formulu)
    ("cantilever", "point"): (lambda P, L, EI: P * L ** 3 / (3 * EI), lambda P, L: P * L, "δ = P·L³/(3·E·I)", "M = P·L"),
    ("cantilever", "udl"): (lambda w, L, EI: w * L ** 4 / (8 * EI), lambda w, L: w * L * L / 2, "δ = w·L⁴/(8·E·I)", "M = w·L²/2"),
    ("simply_supported", "point"): (lambda P, L, EI: P * L ** 3 / (48 * EI), lambda P, L: P * L / 4, "δ = P·L³/(48·E·I)", "M = P·L/4"),
    ("simply_supported", "udl"): (lambda w, L, EI: 5 * w * L ** 4 / (384 * EI), lambda w, L: w * L * L / 8, "δ = 5·w·L⁴/(384·E·I)", "M = w·L²/8"),
}


def _section(params: dict):
    """(I m^4, c m, aciklama)"""
    if "inertia_mm4" in params:
        i = _num(params, "inertia_mm4")
        c = _num(params, "c_mm") / 1000
        return i * 1e-12, c, f"I = {i:g} mm⁴"
    sec = str(params.get("section", "rect")).lower()
    if sec == "rect":
        b, h = _num(params, "b_mm"), _num(params, "h_mm")
        return b * h ** 3 / 12 * 1e-12, h / 2000, f"dikdörtgen {b:g}×{h:g} mm (I = b·h³/12)"
    if sec == "hollow_square":
        b, t = _num(params, "b_mm"), _num(params, "t_mm")
        if 2 * t >= b:
            raise ValueError("Et kalınlığı t, kenarın yarısından küçük olmalı.")
        return (b ** 4 - (b - 2 * t) ** 4) / 12 * 1e-12, b / 2000, f"kare kutu {b:g} mm, et {t:g} mm"
    if sec == "circle":
        d = _num(params, "d_mm")
        return math.pi * d ** 4 / 64 * 1e-12, d / 2000, f"dolu daire Ø{d:g} mm (I = π·d⁴/64)"
    raise ValueError("section rect, hollow_square veya circle olmali (ya da inertia_mm4 + c_mm ver).")


def beam_deflection(params: dict) -> str:
    """Kiris sehimi ve maksimum egilme gerilmesi.
    params: support=cantilever|simply_supported, load=point|udl, length_m, load_n (point) | w_n_per_m (udl), E_gpa=210,
            section=rect(b_mm,h_mm)|hollow_square(b_mm,t_mm)|circle(d_mm) veya inertia_mm4+c_mm"""
    support = str(params.get("support", "cantilever")).lower()
    load = str(params.get("load", "point")).lower()
    if (support, load) not in _BEAMS:
        raise ValueError("support cantilever|simply_supported, load point|udl olmali.")
    L = _num(params, "length_m")
    e = _num(params, "E_gpa", 210) * 1e9
    i, c, desc = _section(params)
    q = _num(params, "load_n" if load == "point" else "w_n_per_m")
    defl_f, mom_f, defl_txt, mom_txt = _BEAMS[(support, load)]
    delta = defl_f(q, L, e * i)
    m = mom_f(q, L)
    sigma = m * c / i
    return (f"**Kiriş hesabı** ({'ankastre' if support == 'cantilever' else 'basit mesnetli'}, "
            f"{'tekil yük' if load == 'point' else 'yayılı yük'})\n\n"
            f"| Büyüklük | Değer | Birim |\n|---|---:|---|\n"
            f"| Kesit | {desc} | |\n| Atalet momenti I | {i * 1e12:.5g} | mm⁴ |\n| Boy L | {L:g} | m |\n"
            f"| Elastisite modülü E | {e / 1e9:g} | GPa |\n"
            f"| Yük | {q:g} | {'N' if load == 'point' else 'N/m'} |\n"
            f"| **Maksimum sehim δ** | **{delta * 1000:.4g}** | mm |\n| Maksimum moment M | {m:.5g} | N·m |\n"
            f"| **Maksimum eğilme gerilmesi σ** | **{sigma / 1e6:.4g}** | MPa |\n\n"
            f"{defl_txt};  {mom_txt};  σ = M·c/I")


def steam_table(params: dict) -> str:
    """Doymus su/buhar tablosu. params: p_min_bar, p_max_bar, n=10 (en fazla 50), fluid='Water'"""
    from CoolProp.CoolProp import PropsSI
    p0, p1 = _num(params, "p_min_bar"), _num(params, "p_max_bar")
    if p1 < p0:
        raise ValueError("p_max_bar, p_min_bar'dan küçük olamaz.")
    n = int(max(1, min(int(_num(params, "n", 10)), 50)))
    fluid = str(params.get("fluid", "Water"))
    rows = ["| P (bar) | Tdoy (°C) | hf (kJ/kg) | hg (kJ/kg) | hfg (kJ/kg) | sf (kJ/kg·K) | sg (kJ/kg·K) |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for k in range(n):
        p = p0 + (p1 - p0) * (k / (n - 1) if n > 1 else 0)
        pa = p * 1e5
        t = PropsSI("T", "P", pa, "Q", 0, fluid) - 273.15
        hf, hg = (PropsSI("H", "P", pa, "Q", q, fluid) / 1000 for q in (0, 1))
        sf, sg = (PropsSI("S", "P", pa, "Q", q, fluid) / 1000 for q in (0, 1))
        rows.append(f"| {p:.3f} | {t:.2f} | {hf:.1f} | {hg:.1f} | {hg - hf:.1f} | {sf:.4f} | {sg:.4f} |")
    return f"**Doymuş {fluid} tablosu** (CoolProp)\n\n" + "\n".join(rows)


CALCS = {"pipe_pressure_drop": pipe_pressure_drop, "beam_deflection": beam_deflection, "steam_table": steam_table}


def run(calc: str, params: dict) -> str:
    """Hata (ValueError, CoolProp) cagirana kalir; tools.eng_calc bunu modele okunur mesaja cevirir."""
    fn = CALCS.get(str(calc))
    if not fn:
        raise ValueError(f"Bilinmeyen hesap '{calc}'. Geçerli: {sorted(CALCS)}")
    return fn(params if isinstance(params, dict) else {})
