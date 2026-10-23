"""
Akışkanlar Mekaniği - Reynolds Sayısı Hesaplama Modülü
Kategori: fluids
"""

def calculate_reynolds(density, velocity, length, dynamic_viscosity):
    """
    Reynolds sayısını hesaplar.

    Parametreler:
        density (float): Akışkan yoğunluğu (kg/m³)
        velocity (float): Akışkan hızı (m/s)
        length (float): Karakteristik uzunluk (m)
        dynamic_viscosity (float): Dinamik viskozite (Pa·s)

    Dönüş:
        float: Reynolds sayısı (boyutsuz)
    """
    reynolds = (density * velocity * length) / dynamic_viscosity
    return reynolds


def flow_type(reynolds):
    """
    Reynolds sayısına göre akış tipini belirler.

    Parametreler:
        reynolds (float): Reynolds sayısı

    Dönüş:
        str: Akış tipi ('Laminar', 'Transitional', 'Turbulent')
    """
    if reynolds < 2300:
        return "Laminar"
    elif reynolds < 4000:
        return "Transitional"
    else:
        return "Turbulent"


if __name__ == "__main__":
    # Test 1: Su boru içindeki akış (laminar)
    re1 = calculate_reynolds(998, 0.5, 0.05, 0.001)
    print(f"Test 1 - Re={re1:.0f}, Akış: {flow_type(re1)}")

    # Test 2: Havada yüksek hızlı akış (turbulent)
    re2 = calculate_reynolds(1.225, 50, 2, 1.81e-5)
    print(f"Test 2 - Re={re2:.0f}, Akış: {flow_type(re2)}")

    # Test 3: Geçiş bölgesi
    re3 = calculate_reynolds(1000, 1, 0.01, 0.001)
    print(f"Test 3 - Re={re3:.0f}, Akış: {flow_type(re3)}")