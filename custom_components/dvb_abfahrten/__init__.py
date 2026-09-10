"""DVB Abfahrten - Abfahrtszeiten der Dresdner Verkehrsbetriebe.

Eigenbau statt Fund: es gibt weder im Home-Assistant-Kern noch in HACS etwas
fuer den Verkehrsverbund Oberelbe. Die beiden allgemeinen
Abfahrts-Integrationen decken ueber 60 Laender ab - fuer EINE schluessellose
Schnittstelle mit so einfacher Antwort ist das mehr Risiko als Gewinn.

Die Abfahrtstafel-Karte liegt im Paket und wird von der Integration selbst
ausgeliefert und angemeldet. Damit ist es eine Installation statt zwei, und
niemand muss eine Lovelace-Ressource von Hand pflegen.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.loader import async_get_integration

from .const import CONF_HALTESTELLEN, DOMAIN
from .coordinator import DvbCoordinator

_LOGGER = logging.getLogger(__name__)

PLATTFORMEN = [Platform.SENSOR]

KARTE_URL = "/dvb_abfahrten/dvb-tafel-card.js"
KARTE_ANGEMELDET = DOMAIN + "_karte"


async def _karte_anmelden(hass: HomeAssistant) -> None:
    """Die Tafel-Karte ausliefern und im Frontend bekannt machen.

    Nur einmal je Start: `add_extra_js_url` haengt die Datei sonst mehrfach in
    jede Seite, und der Browser laedt sie dann auch mehrfach.
    """
    if hass.data.get(KARTE_ANGEMELDET):
        return
    hass.data[KARTE_ANGEMELDET] = True

    datei = Path(__file__).parent / "frontend" / "dvb-tafel-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(KARTE_URL, str(datei), True)]
    )

    # Die Version haengt an der URL, damit ein Update nicht am
    # Browser-Zwischenspeicher haengenbleibt. Sie kommt aus der manifest.json,
    # damit sie nicht an zwei Stellen gepflegt werden muss.
    integration = await async_get_integration(hass, DOMAIN)
    url = "%s?v=%s" % (KARTE_URL, integration.version)

    add_extra_js_url(hass, url)
    await _als_ressource_eintragen(hass, url)
    _LOGGER.debug("Abfahrtstafel-Karte angemeldet: %s", url)


async def _als_ressource_eintragen(hass: HomeAssistant, url: str) -> None:
    """Die Karte zusaetzlich als Lovelace-RESSOURCE fuehren.

    `add_extra_js_url` allein genuegt nicht, und das ist die Lehre aus einem
    echten Fehlerbild: die Karte zeigte auf einem Dashboard "Konfigurations-
    fehler", auf einem anderen lief dieselbe Karte einwandfrei. Der
    Unterschied war ihre POSITION - weit oben wurde sie gezeichnet, bevor das
    ueber `extra_module_url` eingehaengte Modul ausgefuehrt war.

    Lovelace laedt seine Ressourcen dagegen, BEVOR es Karten baut. Genau
    deshalb tragen sich andere Integrationen, die eine Karte mitbringen, hier
    ein - nachgesehen auf einer laufenden Instanz: ha_washdata und bambu_lab
    machen es beide so.

    Beides zusammen ist unschaedlich: die Kartendatei definiert ihr Element
    nur, wenn es noch nicht existiert.

    Im YAML-Modus gibt es keine Ressourcenverwaltung - dann bleibt es bei
    `add_extra_js_url`, und der Fehler oben kann wieder auftreten. Der Nutzer
    traegt die Ressource dort selbst ein.
    """
    lovelace = hass.data.get("lovelace")
    ressourcen = getattr(lovelace, "resources", None)
    if ressourcen is None:
        _LOGGER.debug("Keine Lovelace-Ressourcenverwaltung (YAML-Modus?)")
        return

    try:
        if hasattr(ressourcen, "async_get_info"):
            await ressourcen.async_get_info()

        ohne_version = url.split("?")[0]
        for vorhanden in ressourcen.async_items():
            if vorhanden["url"].split("?")[0] != ohne_version:
                continue
            if vorhanden["url"] == url:
                return
            # Gleiche Datei, andere Version: den Eintrag mitziehen statt einen
            # zweiten anzulegen - sonst sammeln sich mit jedem Update alte
            # Zeilen an, und der Browser laedt die Karte mehrfach.
            await ressourcen.async_update_item(vorhanden["id"], {"url": url})
            return

        await ressourcen.async_create_item({"res_type": "module", "url": url})
    except Exception:  # noqa: BLE001 - eine Karte darf das Setup nicht kippen
        _LOGGER.exception("Ressourceneintrag fehlgeschlagen, %s bleibt", url)


async def async_setup_entry(hass: HomeAssistant, eintrag: ConfigEntry) -> bool:
    """Eintrag einrichten."""
    await _karte_anmelden(hass)

    koordinator = DvbCoordinator(hass, eintrag, async_get_clientsession(hass))
    await koordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[eintrag.entry_id] = koordinator
    await hass.config_entries.async_forward_entry_setups(eintrag, PLATTFORMEN)

    # Ohne diesen Zuhoerer bliebe eine geaenderte Haltestellenauswahl bis zum
    # naechsten Neustart wirkungslos - und niemand wuesste warum.
    eintrag.async_on_unload(eintrag.add_update_listener(_neu_laden))
    return True


async def _neu_laden(hass: HomeAssistant, eintrag: ConfigEntry) -> None:
    await hass.config_entries.async_reload(eintrag.entry_id)


async def async_unload_entry(hass: HomeAssistant, eintrag: ConfigEntry) -> bool:
    """Eintrag entfernen."""
    entladen = await hass.config_entries.async_unload_platforms(eintrag, PLATTFORMEN)
    if entladen:
        hass.data[DOMAIN].pop(eintrag.entry_id, None)
    return entladen


async def async_remove_config_entry_device(
    hass: HomeAssistant, eintrag: ConfigEntry, geraet: DeviceEntry
) -> bool:
    """Erlaubt das Loeschen einer Haltestelle, die nicht mehr eingerichtet ist.

    Ohne diese Funktion bleibt nach dem Entfernen einer Haltestelle ein
    verwaistes Geraet samt Entitaet stehen - sichtbar, dauerhaft
    "nicht verfuegbar" und nicht wegzubekommen.
    """
    eingerichtet = {h["id"] for h in eintrag.options.get(CONF_HALTESTELLEN, [])}
    return not any(kennung[1] in eingerichtet
                   for kennung in geraet.identifiers if kennung[0] == DOMAIN)
