"""Ein Sensor je Haltestelle.

Zustand ist die Wartezeit bis zur naechsten Abfahrt in Minuten - eine Zahl,
die man in einer Kachel anzeigen und in einer Automation vergleichen kann.
Die vollstaendige Tafel haengt als Attribut daran.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DvbCoordinator


async def async_setup_entry(hass: HomeAssistant, eintrag: ConfigEntry,
                            hinzufuegen: AddEntitiesCallback) -> None:
    koordinator: DvbCoordinator = hass.data[DOMAIN][eintrag.entry_id]
    hinzufuegen(HaltestelleSensor(koordinator, h)
                for h in koordinator.haltestellen)


class HaltestelleSensor(CoordinatorEntity[DvbCoordinator], SensorEntity):
    """Wartezeit bis zur naechsten Abfahrt, mit der Tafel als Attribut."""

    _attr_has_entity_name = True
    _attr_name = "Abfahrten"
    _attr_icon = "mdi:tram"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    # BEWUSST OHNE state_class: "Minuten bis zur naechsten Bahn" zu
    # mitteln waere Unsinn, und HA baute daraus stur Langzeitstatistik.

    def __init__(self, koordinator: DvbCoordinator, haltestelle: dict[str, str]) -> None:
        super().__init__(koordinator)
        self._id = haltestelle["id"]
        self._name = haltestelle["name"]
        self._ort = haltestelle["ort"]
        self._attr_unique_id = "%s_%s" % (koordinator.eintrag.entry_id, self._id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            name="%s (%s)" % (self._name, self._ort),
            manufacturer="Verkehrsverbund Oberelbe",
            model="Haltestelle %s" % self._id,
        )

    @property
    def _tafel(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._id)

    @property
    def available(self) -> bool:
        # Eine einzelne ausgefallene Haltestelle soll die uebrigen nicht
        # mitreissen - deshalb haengt die Verfuegbarkeit an DIESER, nicht am
        # Gesamtergebnis des Koordinators.
        return super().available and self._tafel is not None

    @property
    def native_value(self) -> int | None:
        tafel = self._tafel
        if not tafel or not tafel["abfahrten"]:
            return None
        return tafel["abfahrten"][0]["minuten"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tafel = self._tafel or {}
        abfahrten = tafel.get("abfahrten", [])
        naechste = abfahrten[0] if abfahrten else None
        # Die erste Abfahrt, die man bei der aktuellen Gehzeit noch schafft.
        erreichbar = next((a for a in abfahrten if a.get("erreichbar")), None)
        naechste_erreichbar = (
            "%s %s in %d Min." % (erreichbar["linie"], erreichbar["ziel"],
                                  erreichbar["minuten"])
            if erreichbar else None)
        return {
            "haltestelle": self._name,
            "ort": self._ort,
            "haltestelle_id": self._id,
            "anzahl": len(abfahrten),
            # Wieviele Zeilen die Tafel zeigen soll. Geholt werden mehr,
            # weil die nicht mehr erreichbaren herausfallen.
            "anzeigen": self.coordinator.anzahl,
            "naechste": (
                "%s %s in %d Min." % (naechste["linie"], naechste["ziel"],
                                      naechste["minuten"])
                if naechste else "keine Abfahrten"
            ),
            "fussweg_minuten": tafel.get("fussweg_minuten"),
            "fussweg_meter": tafel.get("fussweg_meter"),
            "fussweg_von": tafel.get("fussweg_von"),
            # Je Ausgangspunkt ein Eintrag: "Zuhause" und je
            # angemeldetem Benutzer einer. Die Abfahrtstafel sucht
            # sich daraus den passenden heraus.
            "fusswege": tafel.get("fusswege", {}),
            "naechste_erreichbare": naechste_erreichbar,
            "abfahrten": abfahrten,
            "abgerufen": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"),
        }
