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


def pump_power(params: dict) -> str:
    """Pompa/fan gucu. params: flow_lps, head_m | pressure_kpa, efficiency=0.7, density_kgm3=1000 (fan icin ~1.2), motor_efficiency=1"""
    q = _num(params, "flow_lps") / 1000
    eta = _num(params, "efficiency", 0.7)
    eta_m = _num(params, "motor_efficiency", 1.0)
    if eta > 1 or eta_m > 1:
        raise ValueError("Verimler 0 ile 1 arasında olmalı.")
    rho = _num(params, "density_kgm3", 1000)
    if "pressure_kpa" in params:
        dp = _num(params, "pressure_kpa") * 1000
        head = dp / (rho * G)
    else:
        head = _num(params, "head_m")
        dp = rho * G * head
    hyd = q * dp
    shaft = hyd / eta
    return (f"**Pompa/fan gücü**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n"
            f"| Debi Q | {q * 1000:g} | L/s ({q * 3600:.4g} m³/h) |\n| Basma yüksekliği H | {head:.4g} | m |\n"
            f"| Basınç artışı ΔP | {dp / 1000:.4g} | kPa |\n| Hidrolik güç | {hyd / 1000:.4g} | kW |\n"
            f"| **Mil gücü** (η={eta:g}) | **{shaft / 1000:.4g}** | kW |\n"
            f"| **Elektrik gücü** (η motor={eta_m:g}) | **{shaft / eta_m / 1000:.4g}** | kW |\n\n"
            f"P_hid = ρ·g·Q·H = Q·ΔP;  P_mil = P_hid/η")


def shaft_torsion(params: dict) -> str:
    """Dolu mil burulması. params: power_kw + rpm | torque_nm, d_mm, length_m (opsiyonel, burulma açısı için), G_gpa=79.3"""
    d = _num(params, "d_mm") / 1000
    if "torque_nm" in params:
        t = _num(params, "torque_nm")
    else:
        t = _num(params, "power_kw") * 1000 / (_num(params, "rpm") * 2 * math.pi / 60)
    j = math.pi * d ** 4 / 32
    tau = 16 * t / (math.pi * d ** 3)
    rows = (f"| Mil çapı d | {d * 1000:g} | mm |\n| Tork T | {t:.5g} | N·m |\n"
            f"| **Maksimum kayma gerilmesi τ** | **{tau / 1e6:.4g}** | MPa |\n")
    if "length_m" in params:
        L = _num(params, "length_m")
        g = _num(params, "G_gpa", 79.3) * 1e9
        theta = t * L / (g * j)
        rows += f"| **Burulma açısı θ** (L={L:g} m, G={g / 1e9:g} GPa) | **{math.degrees(theta):.4g}** | derece |\n"
    return ("**Mil burulması** (dolu daire kesit)\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n" + rows +
            "\nT = P/ω;  τ = 16·T/(π·d³);  θ = T·L/(G·J),  J = π·d⁴/32")


_BOLT_AREA = {"M6": 20.1, "M8": 36.6, "M10": 58.0, "M12": 84.3, "M14": 115, "M16": 157, "M20": 245, "M24": 353, "M30": 561}
_BOLT_GRADE = {"4.6": (225, 240), "5.8": (380, 420), "8.8": (600, 640), "10.9": (830, 940), "12.9": (970, 1100)}   # (proof, akma) MPa


def bolt_check(params: dict) -> str:
    """Metrik civata (kaba disli) cekme/kesme kontrolu. params: size=M12 (ya da area_mm2), grade=8.8, axial_n, shear_n (ikisi de opsiyonel, en az biri), n_bolts=1"""
    if "area_mm2" in params:
        a, name = _num(params, "area_mm2"), f"As={_num(params, 'area_mm2'):g} mm²"
    else:
        size = str(params.get("size", "M12")).upper()
        if size not in _BOLT_AREA:
            raise ValueError(f"size şunlardan biri olmalı: {list(_BOLT_AREA)} (ya da area_mm2 ver).")
        a, name = _BOLT_AREA[size], size
    grade = str(params.get("grade", "8.8"))
    if grade not in _BOLT_GRADE:
        raise ValueError(f"grade şunlardan biri olmalı: {list(_BOLT_GRADE)}")
    proof, yld = _BOLT_GRADE[grade]
    n = int(_num(params, "n_bolts", 1))
    if "axial_n" not in params and "shear_n" not in params:
        raise ValueError("'axial_n' ve/veya 'shear_n' gerekli.")
    ax = _num(params, "axial_n", 0, positive=False) / n
    sh = _num(params, "shear_n", 0, positive=False) / n
    if ax < 0 or sh < 0:
        raise ValueError("Yükler negatif olamaz.")
    sig, tau = ax / a, sh / a   # N/mm2 = MPa; kesme icin diş bölgesi (muhafazakar) As kullanılır
    vm = math.sqrt(sig ** 2 + 3 * tau ** 2)
    preload = 0.75 * proof * a
    return (f"**Cıvata kontrolü** ({name}, sınıf {grade}, {n} adet)\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n"
            f"| Gerilme alanı As | {a:g} | mm² |\n| Proof / akma dayanımı | {proof} / {yld} | MPa |\n"
            f"| Cıvata başına çekme σ | {sig:.4g} | MPa |\n| Cıvata başına kesme τ | {tau:.4g} | MPa |\n"
            f"| Eşdeğer gerilme (von Mises) | {vm:.4g} | MPa |\n"
            f"| **Güvenlik katsayısı** (proof/eşdeğer) | **{proof / vm if vm else float('inf'):.3g}** | - |\n"
            f"| Önerilen ön yükleme (0.75·proof·As) | {preload / 1000:.4g} | kN |\n"
            f"| Sıkma torku (K=0.2) | {0.2 * preload * (math.sqrt(a / 0.7854) / 1000):.4g} | N·m |\n\n"
            f"Sıkma torku yaklaşık: T = K·F·d (d ≈ √(As/0.7854); yağlama durumuna göre K değişir). Kesme için As kullanıldı (muhafazakâr).")


def wall_heat(params: dict) -> str:
    """Cok katmanli duzlem duvardan 1-B isi gecisi.
    params: layers=[{thickness_mm, k_wm}, ...], t_in_c, t_out_c, h_in=10, h_out=25 (W/m2K), area_m2=1"""
    layers = params.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("'layers' bir liste olmalı: [{\"thickness_mm\": 200, \"k_wm\": 0.8}, ...]")
    t_in, t_out = _num(params, "t_in_c", positive=False), _num(params, "t_out_c", positive=False)
    h_in, h_out = _num(params, "h_in", 10), _num(params, "h_out", 25)
    area = _num(params, "area_m2", 1)
    res = [("iç taşınım", 1 / h_in)]
    for k, ly in enumerate(layers, 1):
        res.append((f"katman {k} ({_num(ly, 'thickness_mm'):g} mm, k={_num(ly, 'k_wm'):g})", _num(ly, "thickness_mm") / 1000 / _num(ly, "k_wm")))
    res.append(("dış taşınım", 1 / h_out))
    r = sum(x for _, x in res)
    q = (t_in - t_out) / r   # W/m2
    rows, t = [], t_in
    for label, x in res:
        t2 = t - q * x
        rows.append(f"| {label} | {x:.4f} | {t:.2f} → {t2:.2f} |")
        t = t2
    return (f"**Duvardan ısı geçişi** (kararlı hal, 1-B)\n\n| Direnç | R (m²·K/W) | Sıcaklık (°C) |\n|---|---:|---|\n" + "\n".join(rows) +
            f"\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n| Toplam direnç | {r:.4f} | m²·K/W |\n"
            f"| **U değeri** | **{1 / r:.4g}** | W/m²·K |\n| **Isı akısı q** | **{q:.4g}** | W/m² |\n"
            f"| Isı kaybı (A={area:g} m²) | {q * area:.5g} | W |\n\nq = ΔT/ΣR;  R = L/k (iletim), 1/h (taşınım)")


CALCS = {"pipe_pressure_drop": pipe_pressure_drop, "beam_deflection": beam_deflection, "steam_table": steam_table,
         "pump_power": pump_power, "shaft_torsion": shaft_torsion, "bolt_check": bolt_check, "wall_heat": wall_heat}


def run(calc: str, params: dict) -> str:
    """Hata (ValueError, CoolProp) cagirana kalir; tools.eng_calc bunu modele okunur mesaja cevirir."""
    fn = CALCS.get(str(calc))
    if not fn:
        raise ValueError(f"Bilinmeyen hesap '{calc}'. Geçerli: {sorted(CALCS)}")
    return fn(params if isinstance(params, dict) else {})
