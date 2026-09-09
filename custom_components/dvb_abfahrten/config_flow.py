"""Einrichtung ueber die Oberflaeche: suchen, auswaehlen, fertig."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import VvoApi, VvoFehler
from .const import (
    CONF_ANZAHL,
    CONF_MINUTEN,
    CONF_MODUS,
    CONF_STANDORT,
    CONF_HALTESTELLEN,
    CONF_SUCHE,
    DOMAIN,
    MODUS_ANZAHL,
    MODUS_ZEITFENSTER,
    STANDARD_ANZAHL,
    STANDARD_MINUTEN,
)


def _titel(haltestellen: list[dict[str, str]]) -> str:
    if not haltestellen:
        return "DVB Abfahrten"
    if len(haltestellen) == 1:
        return haltestellen[0]["name"]
    return "%s und %d weitere" % (haltestellen[0]["name"], len(haltestellen) - 1)


def _auswahl_schema(kandidaten: list[dict[str, str]],
                    vorbelegt: list[str],
                    anzahl: int) -> vol.Schema:
    optionen = [
        SelectOptionDict(value=h["id"], label="%s (%s)" % (h["name"], h["ort"]))
        for h in kandidaten
    ]
    return vol.Schema({
        vol.Required(CONF_HALTESTELLEN, default=vorbelegt): SelectSelector(
            SelectSelectorConfig(options=optionen, multiple=True,
                                 mode=SelectSelectorMode.LIST)),
        vol.Required(CONF_ANZAHL, default=anzahl): NumberSelector(
            NumberSelectorConfig(min=1, max=20, step=1,
                                 mode=NumberSelectorMode.BOX)),
    })


class DvbConfigFlow(ConfigFlow, domain=DOMAIN):
    """Zwei Schritte: Suchbegriff, dann Mehrfachauswahl."""

    VERSION = 1

    def __init__(self) -> None:
        self._gefunden: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            api = VvoApi(async_get_clientsession(self.hass))
            try:
                self._gefunden = await api.suche_haltestellen(user_input[CONF_SUCHE])
            except VvoFehler:
                fehler["base"] = "keine_verbindung"
            else:
                if not self._gefunden:
                    fehler[CONF_SUCHE] = "nichts_gefunden"
                else:
                    return await self.async_step_auswahl()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_SUCHE): str}),
            errors=fehler,
        )

    async def async_step_auswahl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            gewaehlt = [h for h in self._gefunden
                        if h["id"] in user_input[CONF_HALTESTELLEN]]
            # Verhindert, dass dieselbe Zusammenstellung zweimal angelegt wird.
            await self.async_set_unique_id("-".join(sorted(h["id"] for h in gewaehlt)))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_titel(gewaehlt),
                data={},
                options={CONF_HALTESTELLEN: gewaehlt,
                         CONF_ANZAHL: int(user_input[CONF_ANZAHL])},
            )

        return self.async_show_form(
            step_id="auswahl",
            data_schema=_auswahl_schema(self._gefunden, [], STANDARD_ANZAHL),
            description_placeholders={"anzahl": str(len(self._gefunden))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DvbOptionsFlow()


class DvbOptionsFlow(OptionsFlow):
    """Nachtraeglich Haltestellen hinzufuegen, entfernen oder die Anzahl aendern."""

    def __init__(self) -> None:
        self._gefunden: list[dict[str, str]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        bisher: list[dict[str, str]] = self.config_entry.options.get(
            CONF_HALTESTELLEN, [])
        anzahl = int(self.config_entry.options.get(CONF_ANZAHL, STANDARD_ANZAHL))
        standort = self.config_entry.options.get(CONF_STANDORT)
        modus = self.config_entry.options.get(CONF_MODUS, MODUS_ANZAHL)
        minuten = int(self.config_entry.options.get(CONF_MINUTEN,
                                                    STANDARD_MINUTEN))
        fehler: dict[str, str] = {}

        if user_input is not None:
            begriff = (user_input.get(CONF_SUCHE) or "").strip()
            if not begriff:
                # Ohne Suchbegriff nur die Anzahl aendern - die Haltestellen
                # bleiben, wie sie sind.
                return self.async_create_entry(
                    data={CONF_HALTESTELLEN: bisher,
                          CONF_ANZAHL: int(user_input[CONF_ANZAHL]),
                          CONF_MODUS: user_input[CONF_MODUS],
                          CONF_MINUTEN: int(user_input[CONF_MINUTEN]),
                          CONF_STANDORT: user_input.get(CONF_STANDORT)})
            api = VvoApi(async_get_clientsession(self.hass))
            try:
                self._gefunden = await api.suche_haltestellen(begriff)
            except VvoFehler:
                fehler["base"] = "keine_verbindung"
            else:
                if not self._gefunden:
                    fehler[CONF_SUCHE] = "nichts_gefunden"
                else:
                    self._anzahl = int(user_input[CONF_ANZAHL])
                    self._standort = user_input.get(CONF_STANDORT)
                    self._modus = user_input[CONF_MODUS]
                    self._minuten = int(user_input[CONF_MINUTEN])
                    return await self.async_step_auswahl()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SUCHE, default=""): str,
                # Entweder feste Zeilenzahl oder alles im Zeitfenster.
                # Home Assistant kann Felder nicht abhaengig voneinander
                # ausblenden, deshalb stehen beide Werte immer da - welcher
                # gilt, entscheidet die Betriebsart.
                vol.Required(CONF_MODUS, default=modus): SelectSelector(
                    SelectSelectorConfig(
                        options=[MODUS_ANZAHL, MODUS_ZEITFENSTER],
                        translation_key=CONF_MODUS,
                        mode=SelectSelectorMode.LIST)),
                vol.Required(CONF_ANZAHL, default=anzahl): NumberSelector(
                    NumberSelectorConfig(min=1, max=20, step=1,
                                         mode=NumberSelectorMode.BOX)),
                vol.Required(CONF_MINUTEN, default=minuten): NumberSelector(
                    NumberSelectorConfig(min=5, max=120, step=5,
                                         unit_of_measurement="min",
                                         mode=NumberSelectorMode.BOX)),
                # Leer = Fussweg ab Zuhause. Mit Person oder Geraet wird ab
                # der aktuellen Position gerechnet.
                vol.Optional(CONF_STANDORT,
                             description={"suggested_value": standort}):
                    EntitySelector(EntitySelectorConfig(
                        domain=["person", "device_tracker"])),
            }),
            errors=fehler,
            description_placeholders={
                "bisher": ", ".join(h["name"] for h in bisher) or "keine"},
        )

    async def async_step_auswahl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        bisher: list[dict[str, str]] = self.config_entry.options.get(
            CONF_HALTESTELLEN, [])

        # Die bereits eingerichteten Haltestellen stehen mit zur Auswahl und
        # sind vorbelegt. Ohne das wuerde eine neue Suche die alten still
        # verwerfen - der haeufigste Weg, sich eine Einstellung kaputtzumachen.
        bekannt = {h["id"]: h for h in bisher}
        for h in self._gefunden:
            bekannt.setdefault(h["id"], h)
        kandidaten = list(bekannt.values())

        if user_input is not None:
            gewaehlt = [bekannt[i] for i in user_input[CONF_HALTESTELLEN]]
            return self.async_create_entry(
                data={CONF_HALTESTELLEN: gewaehlt,
                      CONF_ANZAHL: int(user_input[CONF_ANZAHL]),
                      CONF_MODUS: getattr(self, "_modus", MODUS_ANZAHL),
                      CONF_MINUTEN: getattr(self, "_minuten", STANDARD_MINUTEN),
                      CONF_STANDORT: getattr(self, "_standort", None)})

        return self.async_show_form(
            step_id="auswahl",
            data_schema=_auswahl_schema(kandidaten,
                                        [h["id"] for h in bisher],
                                        getattr(self, "_anzahl", STANDARD_ANZAHL)),
        )
