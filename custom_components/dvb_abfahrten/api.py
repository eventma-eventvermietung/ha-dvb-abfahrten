"""Zugriff auf die offene VVO-Schnittstelle.

Bewusst duenn gehalten: zwei Abrufe, etwas Aufraeumen der Antwort, sonst
nichts. Die Fehlerbehandlung sitzt im Koordinator, nicht hier.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientSession

from .const import (
    AUSLASTUNG,
    STEIG_TYP,
    URL_ABFAHRTEN,
    URL_FUSSWEG,
    URL_SUCHE,
    VERKEHRSMITTEL,
    ZUSTAND,
)
from .geo import gk_nach_wgs84

_LOGGER = logging.getLogger(__name__)

# Zeitstempel kommen als "/Date(1788983520000-0000)/". Der zweite Zahlenblock
# ist der Zeitzonenversatz - wer einfach nach Ziffern sucht, erwischt ihn mit
# und rechnet danach falsch.
_ZEIT = re.compile(r"/Date\((\d+)([+-]\d+)?\)/")


class VvoFehler(Exception):
    """Die Schnittstelle war nicht erreichbar oder antwortete unbrauchbar."""


def _zeit(wert: str | None) -> datetime | None:
    if not wert:
        return None
    treffer = _ZEIT.match(wert)
    if not treffer:
        return None
    return datetime.fromtimestamp(int(treffer.group(1)) / 1000, timezone.utc)


class VvoApi:
    """Kleiner Klient fuer Haltestellensuche und Abfahrtstafel."""

    def __init__(self, sitzung: ClientSession) -> None:
        self._sitzung = sitzung

    async def _hole_roh(self, url: str,
                        parameter: dict[str, Any]) -> dict[str, Any]:
        """Abruf ohne die VVO-eigene Statuspruefung (fuer fremde Dienste)."""
        try:
            async with self._sitzung.get(url, params=parameter,
                                         timeout=20) as antwort:
                antwort.raise_for_status()
                return await antwort.json(content_type=None)
        except Exception as fehler:  # noqa: BLE001
            raise VvoFehler(str(fehler)) from fehler

    async def _hole(self, url: str, parameter: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._sitzung.get(url, params=parameter, timeout=20) as antwort:
                antwort.raise_for_status()
                # Der VVO sendet application/json als text/html aus - ohne
                # content_type=None wirft aiohttp hier grundlos.
                daten = await antwort.json(content_type=None)
        except Exception as fehler:  # noqa: BLE001 - bewusst breit, Koordinator entscheidet
            raise VvoFehler(str(fehler)) from fehler

        if daten.get("Status", {}).get("Code") != "Ok":
            raise VvoFehler("Schnittstelle meldet %s" % daten.get("Status"))
        return daten

    async def suche_haltestellen(self, begriff: str) -> list[dict[str, str]]:
        """Haltestellen zu einem Suchbegriff finden."""
        daten = await self._hole(URL_SUCHE, {"format": "json", "limit": "30",
                                             "query": begriff})
        gefunden: list[dict[str, str]] = []
        for eintrag in daten.get("Points", []):
            teile = eintrag.split("|")
            # Strassen kommen als "streetID:..." mit - das sind keine
            # Haltestellen und wuerden bei der Abfahrtstafel ins Leere laufen.
            if len(teile) < 4 or not teile[0].isdigit():
                continue
            # Die Schnittstelle kennt NUR Gauss-Krueger; einen Schalter fuer
            # WGS84 gibt es nicht (coordFormat und coordOutputFormat werden
            # ignoriert, ausprobiert). Deshalb hier einmal umrechnen und
            # mitfuehren - spaeter waere die Herkunft nicht mehr erkennbar.
            try:
                breite, laenge = gk_nach_wgs84(float(teile[5]), float(teile[4]))
            except (ValueError, IndexError):
                breite = laenge = None
            gefunden.append({
                "id": teile[0],
                "name": teile[3],
                "ort": teile[2] or "Dresden",
                "breite": breite,
                "laenge": laenge,
            })
        return gefunden

    async def fussweg(self, von: tuple[float, float],
                      nach: tuple[float, float]) -> dict[str, int] | None:
        """Gehstrecke und Gehzeit zwischen zwei Punkten."""
        url = "%s/%.6f,%.6f;%.6f,%.6f" % (URL_FUSSWEG, von[1], von[0],
                                          nach[1], nach[0])
        daten = await self._hole_roh(url, {"overview": "false"})
        wege = daten.get("routes") or []
        if daten.get("code") != "Ok" or not wege:
            return None
        return {
            "meter": int(round(wege[0]["distance"])),
            # Aufgerundet: eine halbe Minute zu wenig einzuplanen aergert
            # mehr, als eine halbe Minute zu frueh dazustehen.
            "minuten": int(math.ceil(wege[0]["duration"] / 60)),
        }

    async def hole_abfahrten(self, haltestelle_id: str,
                             anzahl: int) -> dict[str, Any]:
        """Abfahrtstafel einer Haltestelle."""
        daten = await self._hole(URL_ABFAHRTEN, {"format": "json",
                                                 "stopid": haltestelle_id,
                                                 "limit": str(anzahl)})
        jetzt = datetime.now(timezone.utc)
        abfahrten = []
        for a in daten.get("Departures", []):
            soll = _zeit(a.get("ScheduledTime"))
            echt = _zeit(a.get("RealTime")) or soll
            if echt is None:
                continue
            verspaetung = int((echt - soll).total_seconds() // 60) if soll else 0
            steig = a.get("Platform") or {}
            abfahrten.append({
                "linie": a.get("LineName"),
                "ziel": a.get("Direction"),
                "verkehrsmittel": VERKEHRSMITTEL.get(a.get("Mot"), a.get("Mot")),
                "steig": steig.get("Name"),
                # "Steig" bei Bahn und Bus, "Gleis" bei der Eisenbahn -
                # die Schnittstelle unterscheidet das selbst.
                "steig_art": STEIG_TYP.get(steig.get("Type")),
                # Bleibt leer, solange der VVO nur "Unknown" liefert.
                "auslastung": AUSLASTUNG.get(a.get("Occupancy")),
                "abfahrt": echt.isoformat(),
                "geplant": soll.isoformat() if soll else None,
                "minuten": max(0, int((echt - jetzt).total_seconds() // 60)),
                "verspaetung": verspaetung,
                "zustand": ZUSTAND.get(a.get("State"), "planmäßig"),
                "faellt_aus": a.get("State") == "Cancelled",
            })
        abfahrten.sort(key=lambda x: x["abfahrt"])
        return {
            "name": daten.get("Name"),
            "ort": daten.get("Place"),
            "abfahrten": abfahrten,
        }
