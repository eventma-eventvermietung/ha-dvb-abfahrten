"""Konstanten der DVB-Abfahrten-Integration."""

from datetime import timedelta

DOMAIN = "dvb_abfahrten"

# Die offene Schnittstelle des VVO. Kein Schluessel, keine Anmeldung - das
# ist derselbe Dienst, den die DVB-Webseite selbst benutzt.
BASIS = "https://webapi.vvo-online.de"
URL_SUCHE = BASIS + "/tr/pointfinder"
URL_ABFAHRTEN = BASIS + "/dm"

# Fussweg-Router von OpenStreetMap. Ohne Schluessel, oeffentlich, und der
# einzige gefundene mit Fussgaenger-Profil - der OSRM-Demoserver kann nur
# Auto. Ein Konto braucht es nicht, dafuer Zurueckhaltung: die Strecke wird
# zwischengespeichert und nur neu berechnet, wenn man sich bewegt hat.
URL_FUSSWEG = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"

# Einmal pro Minute. Haeufiger waere sinnlos: die Echtzeitdaten des VVO
# werden selbst nicht schneller fortgeschrieben, und ein Abfahrtsbrett, das
# man ansieht, wird ohnehin beim Oeffnen neu geladen.
ABSTAND = timedelta(seconds=60)

CONF_HALTESTELLEN = "haltestellen"
CONF_ANZAHL = "anzahl"
CONF_SUCHE = "suche"
CONF_STANDORT = "standort"

# Ab wieviel Metern Bewegung der Fussweg neu berechnet wird. Darunter
# aendert sich die Gehzeit um weniger als eine Minute - und jeder Abruf
# belastet einen fremden, kostenlosen Dienst.
UMWEG_SCHWELLE = 150

STANDARD_ANZAHL = 8

# Die Schnittstelle liefert englische Bezeichner; angezeigt wird deutsch.
VERKEHRSMITTEL = {
    "Tram": "Straßenbahn",
    "CityBus": "Bus",
    "IntercityBus": "Regionalbus",
    "PlusBus": "PlusBus",
    "SuburbanRailway": "S-Bahn",
    "Train": "Zug",
    "Cableway": "Seilbahn",
    "Ferry": "Fähre",
    "HailedSharedTaxi": "Anrufsammeltaxi",
}

# Der Bahnsteig heisst je nach Verkehrsmittel anders. Die Schnittstelle
# unterscheidet das selbst - am Hauptbahnhof kommen beide Arten vor.
STEIG_TYP = {
    "Platform": "Steig",
    "Railtrack": "Gleis",
}

# Auslastung. ACHTUNG: der VVO liefert derzeit ausnahmslos "Unknown" -
# geprueft am 2026-09-09 an Postplatz, Hauptbahnhof, Helmholtzstrasse und
# Koblenzer Strasse, insgesamt ueber 50 Abfahrten. Das Feld ist in der
# Schnittstelle vorgesehen, wird aber nicht befuellt. Die Zuordnung steht
# trotzdem hier: sobald der VVO liefert, erscheint es ohne Codeaenderung.
AUSLASTUNG = {
    "ManySeats": "viele Sitzplätze",
    "FewSeats": "wenige Sitzplätze",
    "StandingRoomOnly": "nur Stehplätze",
    "StandingOnly": "nur Stehplätze",
    "Full": "sehr voll",
}

ZUSTAND = {
    "InTime": "pünktlich",
    "Delayed": "verspätet",
    "Cancelled": "fällt aus",
}
