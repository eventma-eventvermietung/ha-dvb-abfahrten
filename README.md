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
* **Unterwegs: die Haltestellen in deiner Nähe.** Ist ein Benutzer nicht zu
  Hause und meldet die Companion-App einen Standort, zeigt die Karte oben die
  drei nächsten Haltestellen samt Abfahrten.
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

Dort steht auch, **was die Tafel zeigen soll**:

| Betriebsart | Wirkung |
|---|---|
| **feste Anzahl** | immer gleich viele Zeilen, egal wie weit sie reichen |
| **nächste Minuten** | alles, was in den nächsten *x* Minuten fährt – abends wenige Zeilen, morgens viele |

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

**Unterwegs steht oben „In deiner Nähe · ab <Adresse>“**, darunter die
eingestellten Haltestellen. Für eine Karte, die nie unterwegs ist – etwa auf
einem Wandpanel –, lässt sich das abschalten:

```yaml
type: custom:dvb-tafel-card
naehe: false
```

Für ein **Wandpanel ohne Scrollen** gibt es zwei weitere Optionen:

```yaml
type: custom:dvb-tafel-card
naehe: false
fussweg_von: Zuhause   # Weg immer ab Zuhause, egal wer angemeldet ist
max_zeilen: 5          # höchstens so viele Abfahrten, festes Höhenbudget
```

| Option | Wirkung |
|---|---|
| `naehe` | `false` blendet „In deiner Nähe“ aus |
| `fussweg_von` | fester Ausgangspunkt für Fußweg und Erreichbarkeit (z. B. `Zuhause`) |
| `max_zeilen` | Höchstzahl angezeigter Abfahrten, auch im Zeitfenster-Betrieb |

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

## In der Nähe

Gesucht wird nur für Benutzer, die **nicht zu Hause** sind und einen Standort
melden. Einstellbar in den Optionen der Integration: an/aus und der
Suchradius (Standard 1000 m).

Zwei Eigenheiten der VVO-Schnittstelle bestimmen, wie gesucht wird – beide
gemessen, nicht angenommen:

* **Eine einzelne Umkreissuche reicht höchstens rund 550 m weit**, und nicht
  gleichmäßig; `limit` erweitert das nicht. Gesucht wird deshalb am Standort
  und an vier Punkten in 400 m Abstand. Liegen darin weniger als drei
  Haltestellen im Radius, zusätzlich an acht Punkten weiter außen.
* **Das Entfernungsfeld der Antwort ist keine Luftlinie** (gemeldet 485 m bei
  echten 242 m). Die Integration rechnet die Entfernung selbst aus den
  Koordinaten und filtert danach; angezeigt wird der Fußweg.

Rücksicht auf fremde Dienste: der Standort geht **auf 50 m gerundet** an den
VVO; neu gesucht wird nur nach 150 m Bewegung oder nach 15 Minuten. Die
Abfahrten der drei Haltestellen kommen wie alle anderen jede Minute.

## Sensoren

| | |
|---|---|
| Zustand | Minuten bis zur nächsten Abfahrt |
| `abfahrten` | Liste: Linie, Ziel, Steig, Verkehrsmittel, Minuten, Verspätung, Ausfall, Auslastung |
| `fusswege` | Gehzeit und Strecke je Ausgangspunkt |
| `naechste_erreichbare` | die erste Abfahrt, die bei der aktuellen Gehzeit noch zu schaffen ist |

Dazu `sensor.in_der_nahe_abfahrten`: Zustand ist die Zahl der Benutzer, die
gerade unterwegs sind; das Attribut `unterwegs` enthält je Benutzer die
Tafeln der nächsten Haltestellen.

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
