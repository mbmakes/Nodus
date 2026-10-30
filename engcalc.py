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
        raise ValueError(f"'{key}' sayi olmali (gelen: {v!r}).") from None
    if not math.isfinite(v) or (positive and v <= 0):
        raise ValueError(f"'{key}' pozitif ve sonlu olmali (gelen: {v}).")
    return v


def _fluid_props(fluid: str, t_c: float, p_pa: float):
    """(yogunluk kg/m3, dinamik viskozite Pa.s). Akiskan CoolProp'ta yoksa hata verir."""
    from CoolProp.CoolProp import PropsSI
    T = t_c + 273.15
    return PropsSI("D", "T", T, "P", p_pa, fluid), PropsSI("V", "T", T, "P", p_pa, fluid)


def _phase(fluid: str, t_c: float, p_pa: float) -> str:
    """CoolProp faz adi: liquid | gas | supercritical* | twophase."""
    from CoolProp.CoolProp import PhaseSI
    return PhaseSI("T", t_c + 273.15, "P", p_pa, fluid)


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
    phase = _phase(fluid, t_c, p_pa)
    if phase == "twophase":
        raise ValueError(f"{fluid} bu koşulda ({t_c:g} °C, {p_pa / 1e5:.3f} bar) iki fazlı; tek fazlı boru formülü geçersiz. Sıcaklığı ya da basıncı değiştir.")
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
            f"ΔP = f · (L/D) · ρV²/2" + _gas_note(phase, dp, p_pa, fluid, t_c))


def _gas_note(phase: str, dp: float, p_pa: float, fluid: str, t_c: float) -> str:
    """Gaz fazinda Darcy-Weisbach sikistirilamaz kabul eder: faz uyarisi (ornek: 1 bar'da 120 °C 'su' aslinda buhardir) ve ΔP/P siniri."""
    if "gas" not in phase:
        return ""
    note = (f"\n\n**Uyarı:** {fluid} bu koşulda ({t_c:g} °C, {p_pa / 1e5:.3f} bar) gaz fazında; sıvı bekliyorsan basıncı yükselt. "
            "Gaz için bu formül sıkıştırılamaz akış varsayar (ΔP, mutlak basıncın ~%10'undan küçükse geçerlidir).")
    return note + (f" Burada ΔP/P = %{dp / p_pa * 100:.0f}: sonuç GEÇERSİZ, sıkıştırılabilir akış hesabı gerekir." if dp > 0.1 * p_pa else "")


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
        if not isinstance(ly, dict):
            raise ValueError(f"layers[{k - 1}] bir nesne olmalı: {{\"thickness_mm\": 200, \"k_wm\": 0.8}} (gelen: {ly!r}).")
        res.append((f"katman {k} ({_num(ly, 'thickness_mm'):g} mm, k={_num(ly, 'k_wm'):g})", _num(ly, "thickness_mm") / 1000 / _num(ly, "k_wm")))
    res.append(("dış taşınım", 1 / h_out))
    r = sum(x for _, x in res)
    q = (t_in - t_out) / r   # W/m2
    rows, t = [], t_in
    for label, x in res:
        t2 = t - q * x
        rows.append(f"| {label} | {x:.4f} | {t:.2f} → {t2:.2f} |")
        t = t2
    return ("**Duvardan ısı geçişi** (kararlı hal, 1-B)\n\n| Direnç | R (m²·K/W) | Sıcaklık (°C) |\n|---|---:|---|\n" + "\n".join(rows) +
            f"\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n| Toplam direnç | {r:.4f} | m²·K/W |\n"
            f"| **U değeri** | **{1 / r:.4g}** | W/m²·K |\n| **Isı akısı q** | **{q:.4g}** | W/m² |\n"
            f"| Isı kaybı (A={area:g} m²) | {q * area:.5g} | W |\n\nq = ΔT/ΣR;  R = L/k (iletim), 1/h (taşınım)")


def heat_exchanger(params: dict) -> str:
    """Esanjor LMTD yontemi. params: flow=counter|parallel, t_hot_in, t_hot_out, t_cold_in, t_cold_out (°C),
    q_kw | (m_hot_kgs + cp_hot_kjkgk=4.18), u_wm2k (verilirse gerekli alan da hesaplanir)"""
    flow = str(params.get("flow", "counter")).lower()
    if flow not in ("counter", "parallel"):
        raise ValueError("flow counter (karşı akış) veya parallel (paralel akış) olmalı.")
    th1, th2 = _num(params, "t_hot_in", positive=False), _num(params, "t_hot_out", positive=False)
    tc1, tc2 = _num(params, "t_cold_in", positive=False), _num(params, "t_cold_out", positive=False)
    d1, d2 = (th1 - tc2, th2 - tc1) if flow == "counter" else (th1 - tc1, th2 - tc2)
    if d1 <= 0 or d2 <= 0:
        raise ValueError(f"Uç sıcaklık farkları pozitif olmalı (ΔT1={d1:g}, ΔT2={d2:g}); sıcaklıkları ve akış yönünü kontrol et.")
    lmtd = d1 if math.isclose(d1, d2, rel_tol=1e-9) else (d1 - d2) / math.log(d1 / d2)
    if "q_kw" in params:
        q = _num(params, "q_kw") * 1000
    else:
        q = _num(params, "m_hot_kgs") * _num(params, "cp_hot_kjkgk", 4.18) * 1000 * (th1 - th2)
        if q <= 0:
            raise ValueError("Sıcak akışkan soğumalı (t_hot_in > t_hot_out) ya da q_kw ver.")
    rows = (f"| Akış düzeni | {'karşı akış' if flow == 'counter' else 'paralel akış'} | |\n| ΔT1 / ΔT2 | {d1:.4g} / {d2:.4g} | K |\n"
            f"| **LMTD** | **{lmtd:.4g}** | K |\n| Isıl güç Q | {q / 1000:.5g} | kW |\n")
    if "u_wm2k" in params:
        u = _num(params, "u_wm2k")
        rows += f"| Toplam ısı geçiş katsayısı U | {u:g} | W/m²·K |\n| **Gerekli alan A** | **{q / (u * lmtd):.4g}** | m² |\n"
    return ("**Eşanjör (LMTD yöntemi)**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n" + rows +
            "\nLMTD = (ΔT1−ΔT2)/ln(ΔT1/ΔT2);  Q = U·A·LMTD (düzeltme çarpanı F=1: tek geçişli, saf karşı/paralel akış)")


_BUCKLING_K = {"pinned": 1.0, "fixed_free": 2.0, "fixed_pinned": 0.7, "fixed_fixed": 0.5}


def _min_section(params: dict):
    """(en kucuk I m^4, alan m^2 | None, aciklama). Burkulma zayif eksende olur."""
    if "inertia_mm4" in params:
        a = _num(params, "area_mm2") * 1e-6 if "area_mm2" in params else None
        i = _num(params, "inertia_mm4")
        return i * 1e-12, a, f"I = {i:g} mm⁴"
    sec = str(params.get("section", "rect")).lower()
    if sec == "rect":
        b, h = _num(params, "b_mm"), _num(params, "h_mm")
        return min(b * h ** 3, h * b ** 3) / 12 * 1e-12, b * h * 1e-6, f"dikdörtgen {b:g}×{h:g} mm (zayıf eksen)"
    if sec == "hollow_square":
        b, t = _num(params, "b_mm"), _num(params, "t_mm")
        if 2 * t >= b:
            raise ValueError("Et kalınlığı t, kenarın yarısından küçük olmalı.")
        return (b ** 4 - (b - 2 * t) ** 4) / 12 * 1e-12, (b * b - (b - 2 * t) ** 2) * 1e-6, f"kare kutu {b:g} mm, et {t:g} mm"
    if sec == "circle":
        d = _num(params, "d_mm")
        return math.pi * d ** 4 / 64 * 1e-12, math.pi * d * d / 4 * 1e-6, f"dolu daire Ø{d:g} mm"
    raise ValueError("section rect, hollow_square veya circle olmali (ya da inertia_mm4 [+ area_mm2] ver).")


def column_buckling(params: dict) -> str:
    """Euler burkulma yuku. params: length_m, end=pinned|fixed_free|fixed_pinned|fixed_fixed, E_gpa=210, yield_mpa=250,
    load_n (opsiyonel, guvenlik katsayisi icin), section=rect|hollow_square|circle (ya da inertia_mm4 + area_mm2)"""
    end = str(params.get("end", "pinned")).lower()
    if end not in _BUCKLING_K:
        raise ValueError(f"end şunlardan biri olmalı: {list(_BUCKLING_K)}")
    length, e = _num(params, "length_m"), _num(params, "E_gpa", 210) * 1e9
    i, a, desc = _min_section(params)
    le = _BUCKLING_K[end] * length
    pcr = math.pi ** 2 * e * i / le ** 2
    rows = (f"| Kesit | {desc} | |\n| Etkin boy K·L | {le:.4g} (K={_BUCKLING_K[end]:g}) | m |\n"
            f"| **Kritik burkulma yükü Pcr** | **{pcr / 1000:.5g}** | kN |\n")
    note = ""
    if a:
        sig, lam = pcr / a, le / math.sqrt(i / a)
        fy = _num(params, "yield_mpa", 250) * 1e6
        rows += f"| Narinlik λ = K·L/r | {lam:.4g} | - |\n| Kritik gerilme σcr | {sig / 1e6:.4g} | MPa |\n"
        if sig > fy:
            note = f"\n\n**Uyarı:** σcr ({sig / 1e6:.4g} MPa) akma dayanımını ({fy / 1e6:g} MPa) aşıyor; Euler formülü geçersiz (kısa kolon), akma sınırlar."
    if "load_n" in params:
        rows += f"| **Güvenlik katsayısı** (Pcr/yük) | **{pcr / _num(params, 'load_n'):.3g}** | - |\n"
    return ("**Kolon burkulması (Euler)**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n" + rows +
            "\nPcr = π²·E·I/(K·L)²" + note)


def orifice_flow(params: dict) -> str:
    """Orifis/venturi debi (basitlestirilmis, sabit Cd). params: pipe_d_mm, orifice_d_mm, dp_kpa, density_kgm3=1000, cd=0.61"""
    big, small = _num(params, "pipe_d_mm"), _num(params, "orifice_d_mm")
    beta = small / big
    if not 0.1 <= beta <= 0.75:
        raise ValueError(f"β = d/D = {beta:.3f}; bu hesap 0.1–0.75 aralığında geçerli.")
    dp, rho, cd = _num(params, "dp_kpa") * 1000, _num(params, "density_kgm3", 1000), _num(params, "cd", 0.61)
    a0 = math.pi * (small / 1000) ** 2 / 4
    q = cd * a0 * math.sqrt(2 * dp / rho) / math.sqrt(1 - beta ** 4)
    return (f"**Orifis debisi**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n| β = d/D | {beta:.4g} | - |\n"
            f"| Boşaltma katsayısı Cd | {cd:g} | - |\n| Basınç farkı ΔP | {dp / 1000:g} | kPa |\n"
            f"| **Debi Q** | **{q * 1000:.5g}** | L/s ({q * 3600:.4g} m³/h) |\n| Kütlesel debi | {q * rho:.5g} | kg/s |\n\n"
            f"Q = Cd·A₀·√(2ΔP/ρ)/√(1−β⁴). Sabit Cd yaklaşık bir değerdir; ticari ölçümde ISO 5167 (Reynolds'a bağlı Cd) kullan.")


def bearing_life(params: dict) -> str:
    """Rulman nominal omru L10. params: c_kn (dinamik yuk sayisi), p_kn (esdeger yuk), rpm, type=ball|roller"""
    c, p, rpm = _num(params, "c_kn"), _num(params, "p_kn"), _num(params, "rpm")
    kind = str(params.get("type", "ball")).lower()
    if kind not in ("ball", "roller"):
        raise ValueError("type ball (bilyalı) veya roller (makaralı) olmalı.")
    exp = 3.0 if kind == "ball" else 10.0 / 3
    l10 = (c / p) ** exp
    return (f"**Rulman ömrü (L10)**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n| Tip / üs | {'bilyalı' if kind == 'ball' else 'makaralı'} / {exp:.4g} | - |\n"
            f"| C / P | {c / p:.4g} | - |\n| **L10** | **{l10:.5g}** | milyon devir |\n| **L10h** | **{l10 * 1e6 / (60 * rpm):.5g}** | saat ({rpm:g} rpm) |\n\n"
            f"L10 = (C/P)^p;  L10h = L10·10⁶/(60·n). %90 güvenilirlik, ideal yağlama ve hizalama varsayımıyla.")


def psychrometrics(params: dict) -> str:
    """Nemli hava ozellikleri (CoolProp HAPropsSI). params: t_c, rh_percent, pressure_bar=1.01325"""
    from CoolProp.CoolProp import HAPropsSI
    t, rh = _num(params, "t_c", positive=False) + 273.15, _num(params, "rh_percent")
    if rh > 100:
        raise ValueError("rh_percent 0–100 arasında olmalı.")
    p = _num(params, "pressure_bar", 1.01325) * 1e5
    w = HAPropsSI("W", "T", t, "R", rh / 100, "P", p)
    return (f"**Nemli hava** ({t - 273.15:g} °C, %{rh:g} BN, {p / 1e5:.3f} bar)\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n"
            f"| Nem oranı W | {w * 1000:.4g} | g/kg kuru hava |\n| Çiğ noktası | {HAPropsSI('D', 'T', t, 'R', rh / 100, 'P', p) - 273.15:.3g} | °C |\n"
            f"| Yaş termometre | {HAPropsSI('B', 'T', t, 'R', rh / 100, 'P', p) - 273.15:.3g} | °C |\n"
            f"| Entalpi h | {HAPropsSI('H', 'T', t, 'R', rh / 100, 'P', p) / 1000:.4g} | kJ/kg kuru hava |\n"
            f"| Özgül hacim | {HAPropsSI('V', 'T', t, 'R', rh / 100, 'P', p):.4g} | m³/kg kuru hava |")


def npsh_available(params: dict) -> str:
    """Pompa emisinde mevcut NPSH. params: temperature_c=20, surface_pressure_bar=1.01325 (mutlak), static_head_m (sivi seviyesi pompadan yukaridaysa +),
    loss_m=0, fluid='Water', npsh_required_m (opsiyonel, emniyet payi icin)"""
    from CoolProp.CoolProp import PropsSI
    fluid, t = str(params.get("fluid", "Water")), _num(params, "temperature_c", 20, positive=False) + 273.15
    ps = _num(params, "surface_pressure_bar", 1.01325) * 1e5
    head = _num(params, "static_head_m", 0, positive=False)
    loss = _num(params, "loss_m", 0, positive=False)
    rho, pv = PropsSI("D", "T", t, "Q", 0, fluid), PropsSI("P", "T", t, "Q", 0, fluid)
    npsh = (ps - pv) / (rho * G) + head - loss
    rows = (f"| Akışkan | {fluid}, {t - 273.15:g} °C | |\n| Buhar basıncı Pv | {pv / 1000:.4g} | kPa |\n| Yoğunluk ρ | {rho:.1f} | kg/m³ |\n"
            f"| **NPSH mevcut** | **{npsh:.4g}** | m |\n")
    verdict = ""
    if "npsh_required_m" in params:
        req = _num(params, "npsh_required_m")
        rows += f"| NPSH gerekli | {req:g} | m |\n| **Emniyet payı** | **{npsh - req:.3g}** | m |\n"
        if npsh - req < 0.5:
            verdict = "\n\n**Uyarı:** emniyet payı 0,5 m'nin altında; kavitasyon riski var."
    return ("**NPSH (mevcut)**\n\n| Büyüklük | Değer | Birim |\n|---|---:|---|\n" + rows.rstrip("\n") +
            "\n\nNPSHa = (P_yüzey − Pv)/(ρ·g) + z − h_kayıp" + verdict)


CALCS = {"pipe_pressure_drop": pipe_pressure_drop, "beam_deflection": beam_deflection, "steam_table": steam_table,
         "pump_power": pump_power, "shaft_torsion": shaft_torsion, "bolt_check": bolt_check, "wall_heat": wall_heat,
         "heat_exchanger": heat_exchanger, "column_buckling": column_buckling, "orifice_flow": orifice_flow,
         "bearing_life": bearing_life, "psychrometrics": psychrometrics, "npsh_available": npsh_available}


def run(calc: str, params: dict) -> str:
    """Hata (ValueError, CoolProp) cagirana kalir; tools.eng_calc bunu modele okunur mesaja cevirir."""
    fn = CALCS.get(str(calc))
    if not fn:
        raise ValueError(f"Bilinmeyen hesap '{calc}'. Geçerli: {sorted(CALCS)}")
    return fn(params if isinstance(params, dict) else {})
