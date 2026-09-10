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
import time
from typing import Any

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VvoApi, VvoFehler
from .const import (
    ABSTAND,
    HOECHSTZAHL,
    CONF_ANZAHL,
    CONF_HALTESTELLEN,
    CONF_STANDORT,
    DOMAIN,
    CONF_MINUTEN,
    CONF_MODUS,
    CONF_NAEHE,
    CONF_NAEHE_RADIUS,
    MODUS_ZEITFENSTER,
    NAEHE_ANZAHL,
    NAEHE_AUSSEN_ANTEIL,
    NAEHE_NEU_SUCHEN,
    NAEHE_RING,
    STANDARD_NAEHE_RADIUS,
    STANDARD_ANZAHL,
    STANDARD_MINUTEN,
    UMWEG_SCHWELLE,
    VORRAT,
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
        # Haltestellen in der Naehe je unterwegs befindlichem Benutzer. Die
        # SUCHE wird gemerkt (Punkt, Zeitpunkt, Treffer), die Abfahrten
        # nicht - die kommen weiter jede Minute frisch.
        self._naehe_suche: dict[str, dict[str, Any]] = {}
        self.naehe: dict[str, Any] = {}

    @property
    def haltestellen(self) -> list[dict[str, Any]]:
        return self.eintrag.options.get(CONF_HALTESTELLEN, [])

    @property
    def anzahl(self) -> int:
        return int(self.eintrag.options.get(CONF_ANZAHL, STANDARD_ANZAHL))

    @property
    def zeitfenster(self) -> int | None:
        """Minuten, wenn nach Zeit gezeigt wird - sonst None."""
        if self.eintrag.options.get(CONF_MODUS) != MODUS_ZEITFENSTER:
            return None
        return int(self.eintrag.options.get(CONF_MINUTEN, STANDARD_MINUTEN))

    @property
    def naehe_an(self) -> bool:
        return bool(self.eintrag.options.get(CONF_NAEHE, True))

    @property
    def naehe_radius(self) -> int:
        return int(self.eintrag.options.get(CONF_NAEHE_RADIUS,
                                            STANDARD_NAEHE_RADIUS))

    async def _unterwegs(self) -> dict[str, tuple[float, float]]:
        """Benutzer, die NICHT zu Hause sind und einen Standort melden.

        Schluessel ist wie bei den Fusswegen der Name des HA-Benutzers - die
        Karte kennt nur `hass.user.name`. Wer zu Hause ist, braucht keine
        Umgebungssuche: dafuer gibt es die eingestellten Haltestellen.
        """
        weg: dict[str, tuple[float, float]] = {}
        for zustand in self.hass.states.async_all("person"):
            if zustand.state == "home":
                continue
            breite = zustand.attributes.get("latitude")
            laenge = zustand.attributes.get("longitude")
            if breite is None or laenge is None:
                continue
            ort = (float(breite), float(laenge))
            benutzer_id = zustand.attributes.get("user_id")
            benutzer = (await self.hass.auth.async_get_user(benutzer_id)
                        if benutzer_id else None)
            name = (benutzer.name if benutzer and benutzer.name
                    else zustand.attributes.get("friendly_name"))
            if name:
                weg[name] = ort
        return weg

    async def _umkreis(self, punkt: tuple[float, float]) -> list[dict[str, Any]] | None:
        """Haltestellen um einen Punkt, nach ECHTER Luftlinie sortiert.

        Eine einzelne VVO-Suche reicht hoechstens ~550 m weit. Gesucht wird
        am Punkt und an vier Punkten in NAEHE_RING Metern; reicht das nicht
        fuer NAEHE_ANZAHL Treffer, ein zweites Mal auf einem aeusseren Ring.
        Zusammengefuehrt wird ueber die Haltestellen-Id. Die Entfernung kommt aus den Koordinaten, nicht aus
        dem VVO-Feld - das ist keine Luftlinie (siehe api.py).

        None heisst: es kam GAR NICHTS durch (Netz weg). Dann bleibt die
        letzte Suche stehen, statt die Tafel zu leeren.
        """
        b, l = punkt
        gefunden: dict[str, dict[str, Any]] = {}
        erfolg = False

        def ring(abstand: float, anzahl: int) -> list[tuple[float, float]]:
            return [(b + abstand * math.cos(2 * math.pi * k / anzahl) / 111320.0,
                     l + abstand * math.sin(2 * math.pi * k / anzahl)
                     / (111320.0 * math.cos(math.radians(b))))
                    for k in range(anzahl)]

        async def suche(punkte: list[tuple[float, float]]) -> None:
            nonlocal erfolg
            for sb, sl in punkte:
                try:
                    treffer = await self.api.haltestellen_in_der_naehe(sb, sl, 15)
                except VvoFehler as f:
                    _LOGGER.debug("Umgebungssuche bei %.4f,%.4f gescheitert: %s",
                                  sb, sl, f)
                    continue
                erfolg = True
                for t in treffer:
                    t["luftlinie"] = int(round(_luftlinie(b, l, t["breite"],
                                                          t["laenge"])))
                    gefunden.setdefault(t["id"], t)

        def im_radius() -> list[dict[str, Any]]:
            return sorted((t for t in gefunden.values()
                           if t["luftlinie"] <= self.naehe_radius),
                          key=lambda t: t["luftlinie"])

        await suche([(b, l)] + ring(NAEHE_RING, 4))
        if (len(im_radius()) < NAEHE_ANZAHL
                and self.naehe_radius > 2 * NAEHE_RING):
            await suche(ring(self.naehe_radius * NAEHE_AUSSEN_ANTEIL, 8))
        if not erfolg:
            return None
        return im_radius()

    async def _in_der_naehe(self, unterwegs: dict[str, tuple[float, float]],
                            schon_geholt: dict[str, Any],
                            grenze: int) -> dict[str, Any]:
        """Je unterwegs befindlichem Benutzer die naechsten Haltestellen."""
        ergebnis: dict[str, Any] = {}
        jetzt = time.monotonic()
        for name, punkt in unterwegs.items():
            alt = self._naehe_suche.get(name)
            neu_suchen = (
                alt is None
                or _luftlinie(*alt["von"], *punkt) >= UMWEG_SCHWELLE
                or jetzt - alt["zeit"] > NAEHE_NEU_SUCHEN.total_seconds())
            if neu_suchen:
                treffer = await self._umkreis(punkt)
                if treffer is not None:
                    self._naehe_suche[name] = {"von": punkt, "zeit": jetzt,
                                               "stellen": treffer[:NAEHE_ANZAHL]}
            stellen = (self._naehe_suche.get(name) or {}).get("stellen", [])

            tafeln: list[dict[str, Any]] = []
            for h in stellen:
                if h["id"] in schon_geholt:
                    # Liegt eine eingestellte Haltestelle zufaellig in der
                    # Naehe, wird sie nicht ein zweites Mal abgefragt.
                    tafel = dict(schon_geholt[h["id"]])
                    tafel["abfahrten"] = [dict(x) for x in tafel["abfahrten"]]
                else:
                    try:
                        tafel = await self.api.hole_abfahrten(h["id"], grenze)
                    except VvoFehler:
                        continue
                wege = await self._fusswege(h, {name: punkt})
                weg = wege.get(name)
                if weg:
                    for x in tafel["abfahrten"]:
                        x["erreichbar"] = (not x["faellt_aus"]
                                           and x["minuten"] >= weg["minuten"])
                tafeln.append({"haltestelle": h["name"],
                               "haltestelle_id": h["id"],
                               "luftlinie": h["luftlinie"],
                               "weg": weg,
                               "abfahrten": tafel["abfahrten"]})
            ergebnis[name] = {"adresse": await self._adresse(punkt),
                              "haltestellen": tafeln}
        # Wer wieder zu Hause ist, faellt aus dem Merkzettel.
        for name in list(self._naehe_suche):
            if name not in unterwegs:
                del self._naehe_suche[name]
        return ergebnis

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
                # Beim Zeitfenster laesst sich vorher nicht sagen, wieviele
                # Abfahrten hineinfallen - deshalb der Hoechstwert. Die
                # Karte schneidet danach zu.
                grenze = (HOECHSTZAHL if self.zeitfenster
                          else min(self.anzahl + VORRAT, HOECHSTZAHL))
                tafel = await self.api.hole_abfahrten(h["id"], grenze)
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

        # In der Naehe: bewusst NACH den eingestellten Haltestellen und in
        # einem eigenen try - ein Fehler hier darf die Tafel von zu Hause
        # nicht mitreissen.
        if self.naehe_an:
            try:
                self.naehe = await self._in_der_naehe(
                    await self._unterwegs(), ergebnis,
                    HOECHSTZAHL if self.zeitfenster
                    else min(self.anzahl + VORRAT, HOECHSTZAHL))
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Umgebungssuche fehlgeschlagen")
                self.naehe = {}
        else:
            self.naehe = {}

        # Nur aufgeben, wenn ALLE Haltestellen ausfallen. Faellt eine einzelne
        # aus, sollen die uebrigen weiter angezeigt werden statt die ganze
        # Integration auf "nicht verfuegbar" zu setzen.
        if fehler and not ergebnis:
            raise UpdateFailed("; ".join(fehler))
        if fehler:
            _LOGGER.warning("Teilweise keine Daten - %s", "; ".join(fehler))
        return ergebnis
