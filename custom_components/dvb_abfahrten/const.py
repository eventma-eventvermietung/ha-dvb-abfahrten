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

# Rueckwaerts-Geokodierung, um den Ausgangspunkt als Adresse zu zeigen
# statt als Namen. Nominatim verlangt eine aussagekraeftige Kennung mit
# Kontakt - anonyme Abrufe werden geblockt. Ein Abruf faellt nur an, wenn
# sich der Standort ueberhaupt bewegt hat.
URL_ADRESSE = "https://nominatim.openstreetmap.org/reverse"
KENNUNG = ("ha-dvb-abfahrten "
           "(+https://github.com/eventma-eventvermietung/ha-dvb-abfahrten)")

# Einmal pro Minute. Haeufiger waere sinnlos: die Echtzeitdaten des VVO
# werden selbst nicht schneller fortgeschrieben, und ein Abfahrtsbrett, das
# man ansieht, wird ohnehin beim Oeffnen neu geladen.
ABSTAND = timedelta(seconds=60)

CONF_HALTESTELLEN = "haltestellen"
CONF_ANZAHL = "anzahl"
CONF_SUCHE = "suche"
CONF_STANDORT = "standort"
CONF_MODUS = "modus"
CONF_MINUTEN = "minuten"
CONF_NAEHE = "naehe"
CONF_NAEHE_RADIUS = "naehe_radius"

# Haltestellen in der Naehe, wenn jemand unterwegs ist. Drei reichen: mehr
# ist auf einem Handy nicht mehr "auf einen Blick", und jede weitere kostet
# jede Minute einen Abruf beim VVO.
NAEHE_ANZAHL = 3
STANDARD_NAEHE_RADIUS = 1000
# Neu SUCHEN (nicht neu abfragen) nur nach Bewegung oder nach dieser Zeit.
# Die Abfahrten selbst kommen weiter jede Minute.
NAEHE_NEU_SUCHEN = timedelta(minutes=15)
# Auf so viele Meter gerundet geht der Standort an den VVO. Fuer "welche
# Haltestellen sind in der Naehe" genuegt das, und der eigene Aufenthaltsort
# muss nicht metergenau bei einem Dritten landen.
NAEHE_RUNDUNG = 50
# Eine einzelne VVO-Umkreissuche reicht hoechstens ~550 m weit und nicht
# einmal gleichmaessig; `limit` erweitert das nicht (gemessen 2026-09-10 am
# Buero: vom Standort aus kam nur EINE Haltestelle, die naechste - 358 m -
# fehlte). Gesucht wird deshalb am Standort und an vier Punkten in 400 m.
# Der Wert ist gemessen: bei 400 m fanden sich die drei naechsten, bei 600 m
# mehr Treffer, aber ausgerechnet die naechste fehlte.
NAEHE_RING = 400
# Liegen innen weniger als NAEHE_ANZAHL Haltestellen im Radius (Stadtrand),
# wird mit acht Punkten auf diesem Bruchteil des Radius nachgesucht.
NAEHE_AUSSEN_ANTEIL = 0.75

# Zwei Betriebsarten. "anzahl" zeigt immer gleich viele Zeilen, egal wie
# weit sie in die Zukunft reichen; "zeitfenster" zeigt alles, was in den
# naechsten X Minuten faehrt - abends sind das dann wenige, morgens viele.
MODUS_ANZAHL = "anzahl"
MODUS_ZEITFENSTER = "zeitfenster"
STANDARD_MINUTEN = 30

# Ab wieviel Metern Bewegung der Fussweg neu berechnet wird. Darunter
# aendert sich die Gehzeit um weniger als eine Minute - und jeder Abruf
# belastet einen fremden, kostenlosen Dienst.
UMWEG_SCHWELLE = 150

STANDARD_ANZAHL = 8

# Wieviele Abfahrten ZUSAETZLICH geholt werden. Die Tafel zeigt nur noch
# das, was zu Fuss zu schaffen ist - ohne Vorrat blieben von acht
# angeforderten Zeilen drei uebrig, sobald die ersten schon weg sind.
VORRAT = 8
HOECHSTZAHL = 30

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
