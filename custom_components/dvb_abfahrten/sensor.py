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
    hinzufuegen([HaltestelleSensor(koordinator, h)
                 for h in koordinator.haltestellen]
                + [NaeheSensor(koordinator)])


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
            "anzeigen": (None if self.coordinator.zeitfenster
                         else self.coordinator.anzahl),
            "zeitfenster": self.coordinator.zeitfenster,
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


class NaeheSensor(CoordinatorEntity[DvbCoordinator], SensorEntity):
    """Haltestellen um jeden Benutzer, der gerade unterwegs ist.

    Zustand: wieviele Benutzer gerade unterwegs sind und eine Umgebungstafel
    haben. Die Tafeln haengen je Benutzer als Attribut daran; die Karte
    nimmt sich die des Angemeldeten.

    Der Name ergibt `sensor.in_der_nahe_abfahrten` - er endet bewusst auf
    `_abfahrten`, damit ein recorder-Ausschluss `sensor.*_abfahrten` ihn
    mit erfasst. Die Attribute aendern sich jede Minute.
    """

    _attr_has_entity_name = True
    _attr_name = "Abfahrten"
    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, koordinator: DvbCoordinator) -> None:
        super().__init__(koordinator)
        eintrag_id = koordinator.eintrag.entry_id
        self._attr_unique_id = "%s_naehe" % eintrag_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "naehe_%s" % eintrag_id)},
            name="In der Nähe",
            manufacturer="Verkehrsverbund Oberelbe",
            model="Haltestellen am Standort",
        )

    @property
    def native_value(self) -> int:
        return sum(1 for n in self.coordinator.naehe.values()
                   if n.get("haltestellen"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            # Erkennungsmerkmal fuer die Karte - wie haltestelle_id bei den
            # Haltestellen-Sensoren.
            "dvb_naehe": True,
            "aktiv": self.coordinator.naehe_an,
            "radius": self.coordinator.naehe_radius,
            "anzeigen": (None if self.coordinator.zeitfenster
                         else self.coordinator.anzahl),
            "zeitfenster": self.coordinator.zeitfenster,
            "unterwegs": self.coordinator.naehe,
            "abgerufen": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"),
        }

