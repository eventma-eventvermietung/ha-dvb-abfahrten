# DVB Abfahrten

Abfahrtszeiten der **Dresdner Verkehrsbetriebe** für Home Assistant –
mit Fußweg zur Haltestelle und einer Abfahrtstafel als Lovelace-Karte.

Die Daten kommen von der offenen Schnittstelle des **Verkehrsverbunds
Oberelbe** (`webapi.vvo-online.de`). Sie braucht keinen Schlüssel und keine
Anmeldung; es ist derselbe Dienst, den die DVB-Webseite selbst benutzt.

## Was sie kann

* **Eine oder mehrere Haltestellen**, über die Oberfläche gesucht und
  ausgewählt – ohne Nummern nachschlagen zu müssen.
* Je Haltestelle ein Sensor: **Minuten bis zur nächsten Abfahrt**, die
  vollständige Tafel als Attribut.
* Linie, Ziel, **Steig bzw. Gleis**, Verkehrsmittel, Sollzeit, Echtzeit,
  Verspätung und Ausfälle.
* **Fußweg zur Haltestelle**, berechnet für jeden angemeldeten Benutzer
  einzeln – die Karte zeigt jedem, was *er* noch schafft.
* Eine mitgelieferte **Abfahrtstafel-Karte**; sie muss nicht getrennt
  installiert werden.

## Installation

### Über HACS

1. In HACS oben rechts auf die drei Punkte → **Benutzerdefinierte
   Repositories**.
2. Adresse `https://github.com/eventma-eventvermietung/ha-dvb-abfahrten`
   eintragen, Kategorie **Integration**.
3. „DVB Abfahrten" herunterladen und **Home Assistant neu starten**.
   Ein Neuladen genügt bei einer neuen Integration nicht.

### Von Hand

Den Ordner `custom_components/dvb_abfahrten` in das eigene
`config/custom_components/` kopieren und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → DVB Abfahrten*

1. Haltestelle suchen (zum Beispiel `Postplatz` oder `Koblenzer`).
2. Aus den Treffern **eine oder mehrere** auswählen und festlegen, wie viele
   Abfahrten angezeigt werden sollen.

Später lässt sich über *Konfigurieren* jederzeit eine Haltestelle
hinzufügen oder entfernen; die bisherigen bleiben dabei ausgewählt.

## Die Karte

```yaml
type: custom:dvb-tafel-card
```

Mehr braucht es nicht: **ohne Angabe zeigt die Karte alle eingerichteten
Haltestellen.** Wer später eine hinzufügt, muss das Dashboard nicht
anfassen. Einzelne Haltestellen lassen sich auswählen:

```yaml
type: custom:dvb-tafel-card
entities:
  - sensor.postplatz_dresden_abfahrten
```

**Abfahrten, die man zu Fuß nicht mehr erreicht, werden ausgeblendet.** Die
Integration holt deshalb mehr Abfahrten, als angezeigt werden – sonst blieben
von acht angeforderten Zeilen drei übrig, sobald die ersten schon weg sind.

## Der Fußweg

Berechnet über den Fußgänger-Router von OpenStreetMap
(`routing.openstreetmap.de`), ohne Schlüssel. Ausgangspunkt ist der Standort
des **angemeldeten Benutzers**, sofern eine `person` mit Standort dazu
existiert – sonst der in Home Assistant hinterlegte Wohnort.

Angezeigt wird nicht der Name des Benutzers, sondern die **Adresse**, an der
der Weg beginnt – ermittelt über Nominatim. Der Name sagt nichts darüber, wo
man gerade steht.

Die Strecke wird zwischengespeichert und nur neu berechnet, wenn der
Ausgangspunkt sich um mehr als 150 Meter verschoben hat; die Adresse wird je
Punkt einmal erfragt. Ein fremder, kostenloser Dienst ist kein
Selbstbedienungsladen.

## Sensoren

| | |
|---|---|
| Zustand | Minuten bis zur nächsten Abfahrt |
| `abfahrten` | Liste: Linie, Ziel, Steig, Verkehrsmittel, Minuten, Verspätung, Ausfall, Auslastung |
| `fusswege` | Gehzeit und Strecke je Ausgangspunkt |
| `naechste_erreichbare` | die erste Abfahrt, die bei der aktuellen Gehzeit noch zu schaffen ist |

Die Sensoren tragen bewusst **keine `state_class`** – „Minuten bis zur
nächsten Bahn" zu mitteln wäre ohne Aussage. Wer die Aufzeichnung sparen
will, nimmt sie aus dem `recorder`:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.*_abfahrten
```

## Bekannte Einschränkung: Auslastung

Die Schnittstelle sieht ein Feld `Occupancy` vor. Bei allen Stichproben im
September 2026 – über 50 Abfahrten an fünf Haltestellen, alle Verkehrsmittel,
auch mit dem vollständigen POST-Rumpf der DVB-App – stand dort ausnahmslos
`Unknown`. Die Übersetzung ist trotzdem enthalten: sobald der VVO Daten
liefert, erscheinen sie ohne Änderung am Code.

## Symbol

Das Marken-Symbol liegt unter `custom_components/dvb_abfahrten/brand/` und
wird von Home Assistant ab 2026.3 direkt von dort ausgeliefert – ein Umweg
über die Marken-Sammlung ist dafür nicht nötig.

Es ist ein **eigener Entwurf**: weder das Logo der DVB noch das amtliche
Haltestellenzeichen, beides ist geschützt.

## Dank

An den **Verkehrsverbund Oberelbe** für eine offene Schnittstelle ohne
Anmeldezwang und an **OpenStreetMap** für den Router.

Dieses Projekt steht in keiner Verbindung zur DVB AG oder zum VVO.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
