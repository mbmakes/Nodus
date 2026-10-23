"""
Akışkanlar Mekaniği Modülü
SI birim sistemi kullanılır.
"""
import math


def calculate_reynolds(density, velocity, length, dynamic_viscosity):
    """
    Reynolds Sayısı hesaplar ve akış rejimini etiketler.

    Args:
        density: Özkütle [kg/m³]
        velocity: Hız [m/s]
        length: Karakteristik uzunluk (çap) [m]
        dynamic_viscosity: Dinamik viskozite [Pa·s]

    Returns:
        dict: {'reynolds': Re, 'regime': str}
    """
    Re = (density * velocity * length) / dynamic_viscosity
    if Re < 2300:
        regime = "Laminer"
    elif Re < 4000:
        regime = "Geçiş"
    else:
        regime = "Türbülanslı"
    return {"reynolds": Re, "regime": regime}


def calculate_pipe_friction_loss(f, length, diameter, velocity, g=9.81):
    """
    Darcy-Weisbach denklemi ile boru içi basınç kaybı (h_f).

    Args:
        f: Darcy sürtünme katsayısı [-]
        length: Boru uzunluğu [m]
        diameter: Boru çapı [m]
        velocity: Akış hızı [m/s]
        g: Yerçekimi ivmesi [m/s²]

    Returns:
        float: Basınç kaybı [m]
    """
    h_f = f * (length / diameter) * (velocity ** 2 / (2 * g))
    return h_f


def solve_friction_factor(reynolds, roughness, diameter, tol=1e-12, max_iter=100):
    """
    Colebrook-White bağıntısını iteratif çözer.

    1/sqrt(f) = -2.0 * log10(roughness/(3.7*diameter) + 2.51/(Re*sqrt(f)))

    Args:
        reynolds: Reynolds sayısı [-]
        roughness: Pürüzlülük [m]
        diameter: Boru çapı [m]
        tol: Yakınsama toleransı
        max_iter: Maksimum iterasyon

    Returns:
        float: Darcy sürtünme katsayısı [-]
    """
    if reynolds < 2300:
        return 64.0 / reynolds

    # Başlangıç tahmini (Swamee-Jain)
    f = 0.25 / (math.log10(roughness / (3.7 * diameter) + 5.74 / reynolds ** 0.9)) ** 2

    for _ in range(max_iter):
        f_new = (-2.0 * math.log10(
            roughness / (3.7 * diameter) + 2.51 / (reynolds * math.sqrt(f))
        )) ** (-2)
        if abs(f_new - f) < tol:
            return f_new
        f = f_new

    return f
