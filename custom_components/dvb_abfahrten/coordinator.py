"""Holt Abfahrten und berechnet den Fussweg zur Haltestelle.

Der Fussweg wird fuer JEDEN angemeldeten Benutzer getrennt berechnet, nicht
nur einmal. Grund: ein Sensor-Attribut ist fuer alle gleich, aber die Frage
"schaffe ich die noch?" haengt daran, wo der Fragende gerade steht. Die
Abfahrtstafel ist eine Markdown-Karte, und die wird je angemeldetem Benutzer
gerendert - sie kann sich also den passenden Wert heraussuchen.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VvoApi, VvoFehler
from .const import (
    ABSTAND,
    CONF_ANZAHL,
    CONF_HALTESTELLEN,
    CONF_STANDORT,
    DOMAIN,
    STANDARD_ANZAHL,
    UMWEG_SCHWELLE,
)

_LOGGER = logging.getLogger(__name__)

ZUHAUSE = "Zuhause"


def _luftlinie(b1: float, l1: float, b2: float, l2: float) -> float:
    """Meter zwischen zwei Punkten."""
    r = 6371000.0
    db, dl = math.radians(b2 - b1), math.radians(l2 - l1)
    a = (math.sin(db / 2) ** 2
         + math.cos(math.radians(b1)) * math.cos(math.radians(b2))
         * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


class DvbCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Ein Abruf je Minute fuer alle Haltestellen des Eintrags."""

    def __init__(self, hass: HomeAssistant, eintrag: ConfigEntry,
                 sitzung: ClientSession) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=ABSTAND)
        self.eintrag = eintrag
        self.api = VvoApi(sitzung)
        # Schluessel: (Haltestellen-Id, Ausgangspunkt-Name). Gemerkt wird, von
        # WO aus gerechnet wurde - der Router wird nur erneut gefragt, wenn
        # sich der Ausgangspunkt nennenswert verschoben hat. Ein oeffentlicher
        # OSM-Dienst ist kein Selbstbedienungsladen, und der Weg von zuhause
        # zur Haltestelle aendert sich nie.
        self._fussweg: dict[tuple[str, str], dict[str, Any]] = {}
        # Adressen je Ausgangspunkt, auf vier Nachkommastellen gerundet
        # (rund elf Meter) - feiner braucht es niemand, und Nominatim soll
        # nicht fuer jeden Meter Bewegung befragt werden.
        self._adressen: dict[tuple[float, float], str | None] = {}

    @property
    def haltestellen(self) -> list[dict[str, Any]]:
        return self.eintrag.options.get(CONF_HALTESTELLEN, [])

    @property
    def anzahl(self) -> int:
        return int(self.eintrag.options.get(CONF_ANZAHL, STANDARD_ANZAHL))

    async def _ausgangspunkte(self) -> dict[str, tuple[float, float]]:
        """Alle Orte, von denen aus gerechnet wird.

        Der Schluessel ist der Name des HOME-ASSISTANT-BENUTZERS, nicht der
        der Person - denn genau diesen Namen reicht die Markdown-Karte als
        Variable `user` durch. Der Anzeigename der Person kann davon
        abweichen ("Anna Beispiel" gegenueber "Anna"), deshalb wird er
        zusaetzlich als zweiter Schluessel hinterlegt.
        """
        punkte: dict[str, tuple[float, float]] = {
            ZUHAUSE: (self.hass.config.latitude, self.hass.config.longitude)
        }
        for zustand in self.hass.states.async_all("person"):
            breite = zustand.attributes.get("latitude")
            laenge = zustand.attributes.get("longitude")
            if breite is None or laenge is None:
                continue
            ort = (float(breite), float(laenge))
            anzeigename = zustand.attributes.get("friendly_name")
            if anzeigename:
                punkte[anzeigename] = ort
            benutzer_id = zustand.attributes.get("user_id")
            if benutzer_id:
                benutzer = await self.hass.auth.async_get_user(benutzer_id)
                if benutzer and benutzer.name:
                    punkte[benutzer.name] = ort
        return punkte

    async def _adresse(self, punkt: tuple[float, float]) -> str | None:
        """Adresse eines Ausgangspunkts, gemerkt je Punkt."""
        schluessel = (round(punkt[0], 4), round(punkt[1], 4))
        if schluessel not in self._adressen:
            self._adressen[schluessel] = await self.api.adresse(punkt)
        return self._adressen[schluessel]

    async def _koordinaten_nachtragen(self) -> None:
        """Aeltere Eintraege kennen die Koordinaten noch nicht."""
        fehlend = [h for h in self.haltestellen if h.get("breite") is None]
        if not fehlend:
            return
        haltestellen = list(self.haltestellen)
        geaendert = False
        for h in fehlend:
            try:
                treffer = await self.api.suche_haltestellen(h["name"])
            except VvoFehler:
                continue
            passend = next((t for t in treffer if t["id"] == h["id"]), None)
            if passend:
                h["breite"], h["laenge"] = passend["breite"], passend["laenge"]
                geaendert = True
        if geaendert:
            neu = dict(self.eintrag.options)
            neu[CONF_HALTESTELLEN] = haltestellen
            self.hass.config_entries.async_update_entry(self.eintrag, options=neu)

    async def _fusswege(self, h: dict[str, Any],
                        punkte: dict[str, tuple[float, float]]) -> dict[str, Any]:
        if h.get("breite") is None:
            return {}
        ergebnis: dict[str, Any] = {}
        ziel = (h["breite"], h["laenge"])
        for name, von in punkte.items():
            schluessel = (h["id"], name)
            alt = self._fussweg.get(schluessel)
            if alt and _luftlinie(*alt["von"], *von) < UMWEG_SCHWELLE:
                ergebnis[name] = alt["strecke"]
                continue
            try:
                strecke = await self.api.fussweg(von, ziel)
            except VvoFehler as fehler:
                _LOGGER.debug("Fussweg %s -> %s nicht berechenbar: %s",
                              name, h["name"], fehler)
                if alt:
                    ergebnis[name] = alt["strecke"]
                continue
            if strecke:
                # Die Adresse gehoert zum Ausgangspunkt, nicht zur
                # Haltestelle - deshalb einmal je Punkt merken und nicht
                # je Haltestelle neu erfragen.
                strecke = dict(strecke)
                strecke["adresse"] = await self._adresse(von)
                self._fussweg[schluessel] = {"von": von, "strecke": strecke}
                ergebnis[name] = strecke
        return ergebnis

    async def _async_update_data(self) -> dict[str, Any]:
        await self._koordinaten_nachtragen()
        punkte = await self._ausgangspunkte()

        # Ein fest eingestellter Standort ueberschreibt, welcher Wert in den
        # EINZELNEN Attributen landet (die Automationen sehen). Die Tafel
        # nimmt trotzdem den des angemeldeten Benutzers.
        fest = self.eintrag.options.get(CONF_STANDORT)
        standard = ZUHAUSE
        if fest and (z := self.hass.states.get(fest)):
            if z.attributes.get("latitude") is not None:
                punkte[fest] = (float(z.attributes["latitude"]),
                                float(z.attributes["longitude"]))
                standard = fest

        ergebnis: dict[str, Any] = {}
        fehler: list[str] = []
        for h in self.haltestellen:
            try:
                tafel = await self.api.hole_abfahrten(h["id"], self.anzahl)
            except VvoFehler as f:
                fehler.append("%s: %s" % (h["name"], f))
                continue

            wege = await self._fusswege(h, punkte)
            tafel["fusswege"] = wege
            weg = wege.get(standard) or wege.get(ZUHAUSE)
            if weg:
                tafel["fussweg_minuten"] = weg["minuten"]
                tafel["fussweg_meter"] = weg["meter"]
                tafel["fussweg_von"] = standard
                for a in tafel["abfahrten"]:
                    a["erreichbar"] = (not a["faellt_aus"]
                                       and a["minuten"] >= weg["minuten"])
            ergebnis[h["id"]] = tafel

        # Nur aufgeben, wenn ALLE Haltestellen ausfallen. Faellt eine einzelne
        # aus, sollen die uebrigen weiter angezeigt werden statt die ganze
        # Integration auf "nicht verfuegbar" zu setzen.
        if fehler and not ergebnis:
            raise UpdateFailed("; ".join(fehler))
        if fehler:
            _LOGGER.warning("Teilweise keine Daten - %s", "; ".join(fehler))
        return ergebnis
