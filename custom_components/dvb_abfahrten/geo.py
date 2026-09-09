"""Gauss-Krueger (Bessel/Potsdam) nach WGS84.

Der VVO liefert Haltestellen-Koordinaten ausschliesslich in Gauss-Krueger,
Streifen 4 - es gibt keinen Schalter fuer WGS84 (ausprobiert:
coordFormat/coordOutputFormat werden ignoriert). Ohne Umrechnung koennte man
keine Wegezeit berechnen, denn jeder Router will Laenge und Breite.

`pyproj` ist im Home-Assistant-Container NICHT vorhanden, und eine
Abhaengigkeit dafuer nachzuziehen waere unverhaeltnismaessig - die
Umrechnung ist eine geschlossene Formel.

Zwei Schritte:
  1. Gauss-Krueger -> geographisch auf dem Bessel-Ellipsoid (Reihenentwicklung)
  2. Bessel/Potsdam -> WGS84 ueber eine 7-Parameter-Helmert-Transformation

Genauigkeit: wenige Meter. Fuer einen Fussweg zur Haltestelle ist das weit
mehr als genug - der Router faengt ohnehin auf dem naechsten Gehweg an.

GEPRUEFT gegen bekannte Punkte, siehe geo_pruefen.py.
"""

from __future__ import annotations

import math

# Bessel 1841
_A_BESSEL = 6377397.155
_EE_BESSEL = 0.0066743722296294277832
# WGS84
_A_WGS = 6378137.0
_EE_WGS = 0.00669437999013

# Helmert, Potsdam/DHDN -> WGS84 (bundesweiter Mittelwert)
_DX, _DY, _DZ = 591.28, 81.35, 396.39
_RX = -7.16069806998785e-06
_RY = 3.56822869296619e-07
_RZ = 7.06858347057704e-06
_M = 0.00000982


def _bessel_nach_wgs84(breite: float, laenge: float) -> tuple[float, float]:
    """Datumswechsel ueber kartesische Koordinaten."""
    b = math.radians(breite)
    l = math.radians(laenge)
    n = _A_BESSEL / math.sqrt(1 - _EE_BESSEL * math.sin(b) ** 2)

    x = n * math.cos(b) * math.cos(l)
    y = n * math.cos(b) * math.sin(l)
    z = n * (1 - _EE_BESSEL) * math.sin(b)

    xn = _DX + (1 + _M) * (x + _RZ * y - _RY * z)
    yn = _DY + (1 + _M) * (-_RZ * x + y + _RX * z)
    zn = _DZ + (1 + _M) * (_RY * x - _RX * y + z)

    # Kartesisch zurueck nach geographisch, iterativ (konvergiert in wenigen
    # Schritten; ein geschlossener Ausdruck waere hier unnoetig komplex).
    s = math.sqrt(xn * xn + yn * yn)
    bn = math.atan2(zn, s * (1 - _EE_WGS))
    for _ in range(8):
        nn = _A_WGS / math.sqrt(1 - _EE_WGS * math.sin(bn) ** 2)
        bn = math.atan2(zn + _EE_WGS * nn * math.sin(bn), s)
    ln = math.atan2(yn, xn)
    return math.degrees(bn), math.degrees(ln)


def _meridianbogen(breite_rad: float) -> float:
    """Bogenlaenge vom Aequator bis zur Breite, auf dem Bessel-Ellipsoid.

    Numerisch integriert (Simpson) statt ueber eine Reihe mit auswendig
    gelernten Konstanten. Der erste Versuch benutzte eine solche Reihe und lag
    zehn Kilometer daneben - eine Formel, die man nicht nachrechnen kann, ist
    eine Vermutung.
    """
    n = 2000
    h = breite_rad / n
    def f(x):
        return (1 - _EE_BESSEL * math.sin(x) ** 2) ** -1.5
    summe = f(0) + f(breite_rad)
    for i in range(1, n):
        summe += f(i * h) * (4 if i % 2 else 2)
    return _A_BESSEL * (1 - _EE_BESSEL) * summe * h / 3


def _fusspunktbreite(hoch: float) -> float:
    """Breite, deren Meridianbogen dem Hochwert entspricht (Newton)."""
    b = hoch / (_A_BESSEL * (1 - _EE_BESSEL))
    for _ in range(12):
        abweichung = _meridianbogen(b) - hoch
        ableitung = _A_BESSEL * (1 - _EE_BESSEL) *             (1 - _EE_BESSEL * math.sin(b) ** 2) ** -1.5
        b -= abweichung / ableitung
        if abs(abweichung) < 0.0001:
            break
    return b


def gk_nach_wgs84(rechts: float, hoch: float) -> tuple[float, float]:
    """Gauss-Krueger-Koordinaten (Rechtswert, Hochwert) nach Breite/Laenge."""
    streifen = math.floor(rechts / 1000000)
    bf = _fusspunktbreite(hoch)

    co = math.cos(bf)
    # Zweite numerische Exzentrizitaet, quadriert und mit cos^2 gewichtet
    ee2 = _EE_BESSEL / (1 - _EE_BESSEL)
    g2 = ee2 * co * co
    # Querkruemmungshalbmesser an der Fusspunktbreite
    g1 = _A_BESSEL / math.sqrt(1 - _EE_BESSEL * math.sin(bf) ** 2)
    t = math.tan(bf)
    fa = (rechts - streifen * 1000000 - 500000) / g1

    breite = bf - (fa ** 2) * t * (1 + g2) / 2         + (fa ** 4) * t * (5 + 3 * t * t + 6 * g2 - 6 * g2 * t * t) / 24         - (fa ** 6) * t * (61 + 90 * t * t + 45 * t ** 4) / 720
    dl = fa - (fa ** 3) * (1 + 2 * t * t + g2) / 6         + (fa ** 5) * (1 + 28 * t * t + 24 * t ** 4) / 120

    return _bessel_nach_wgs84(math.degrees(breite),
                              streifen * 3 + math.degrees(dl / co))
