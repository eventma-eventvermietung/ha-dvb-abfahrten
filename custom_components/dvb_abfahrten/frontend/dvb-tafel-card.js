/*
 * DVB Abfahrtstafel - Lovelace-Karte zur Integration dvb_abfahrten.
 *
 * Warum eine eigene Karte statt Markdown: eine Haltestellentafel lebt von der
 * Anordnung - Liniennummer im Kasten, Ziel, Minuten rechtsbuendig. Markdown
 * kann das nicht, und die Formatierung ueber HTML einzuschmuggeln waere ein
 * Kampf gegen die Bereinigung der Karte.
 *
 * Der zweite Grund wiegt schwerer: die Karte kennt ueber `hass.user.name` den
 * ANGEMELDETEN Benutzer. Der Fussweg wird von der Integration je Person
 * berechnet und mitgeliefert; hier wird der passende herausgesucht. Ein
 * Sensor-Attribut allein koennte das nicht - es ist fuer alle gleich.
 *
 * Ohne `entities` in der Konfiguration zeigt die Karte automatisch JEDE
 * Haltestelle der Integration. Wer eine hinzufuegt, muss das Dashboard nicht
 * anfassen.
 */

const FARBEN = {
  "Straßenbahn": ["#f6c700", "#1a1a1a"],
  "Bus": ["#0075bf", "#ffffff"],
  "Regionalbus": ["#0075bf", "#ffffff"],
  "PlusBus": ["#00843d", "#ffffff"],
  "S-Bahn": ["#008d4f", "#ffffff"],
  "Zug": ["#6b7280", "#ffffff"],
  "Fähre": ["#0aa0d9", "#ffffff"],
  "Seilbahn": ["#8b5cf6", "#ffffff"],
};

// Die Version steht in der Konsole, sobald die Datei laeuft. Damit ist mit
// einem Blick zu sagen, WELCHE Fassung ein Browser tatsaechlich ausfuehrt -
// genau die Frage, an der die letzte Fehlersuche haengenblieb.
const VERSION = "1.1.2";
console.info("%c DVB-Tafel %c " + VERSION + " ",
             "background:#f6c700;color:#1a1a1a;font-weight:700",
             "background:#1a1a1a;color:#f6c700");

class DvbTafelCard extends HTMLElement {
  setConfig(config) {
    // NIE werfen. Home Assistant zeigt fuer jeden Fehler hier nur den roten
    // Kasten "Konfigurationsfehler" und verschluckt den Grund - drei
    // Fehlersuchen sind daran gescheitert. Also selbst abfangen und lesbar
    // in die Karte schreiben.
    try {
      this._config = config || {};
      this._aufbauen();
      this._zeichne();
    } catch (e) {
      this._zeigeFehler("setConfig", e);
    }
  }

  // Der Schattenbaum darf nur EINMAL entstehen. Home Assistant ruft
  // setConfig erneut auf, sobald sich die Dashboard-Konfiguration aendert -
  // ein zweites attachShadow wirft dann NotSupportedError, und die Karte
  // zeigt nur noch "Konfigurationsfehler".
  _aufbauen() {
    if (this.shadowRoot) { return; }
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 12px 14px 8px 14px; }
        .halt { margin-bottom: 14px; }
        .bereich {
          font-size: .72rem; font-weight: 600; letter-spacing: .06em;
          text-transform: uppercase; color: var(--secondary-text-color);
          margin: 2px 0 8px 0;
        }
        .halt:last-child { margin-bottom: 6px; }
        .kopf {
          display: flex; align-items: baseline; justify-content: space-between;
          gap: 10px; border-bottom: 1px solid var(--divider-color);
          padding-bottom: 6px; margin-bottom: 6px;
        }
        .name { font-size: 1.12rem; font-weight: 600; }
        .weg { font-size: .78rem; color: var(--secondary-text-color); white-space: nowrap; }
        .zeile {
          display: grid; grid-template-columns: 2.6em 1fr auto;
          align-items: center; gap: 10px; padding: 3px 0;
        }
        .linie {
          font-weight: 700; font-size: .92rem; text-align: center;
          border-radius: 4px; padding: 2px 0; line-height: 1.35;
        }
        .ziel {
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }
        .ab {
          font-variant-numeric: tabular-nums; font-weight: 600;
          text-align: right; white-space: nowrap;
        }
        .verspaetet { color: var(--warning-color, #e8a33d); font-weight: 600; }
        .aus { color: var(--error-color, #db4437); font-weight: 600; }
        .leer { color: var(--secondary-text-color); font-size: .85rem; padding: 4px 0; }
        /* Zweite Zeile: erscheint nur, wenn es etwas zu sagen gibt. Eine
           dauerhaft leere Zeile wuerde die Tafel nur auseinanderziehen. */
        .dazu {
          grid-column: 2 / 4; font-size: .74rem; color: var(--secondary-text-color);
          margin: -2px 0 3px 0;
        }
        .steig { font-weight: 600; }
        .fuss { font-size: .72rem; color: var(--secondary-text-color);
                text-align: right; margin-top: 2px; }
      </style>
      <ha-card><div id="inhalt"></div><div class="fuss" id="fuss"></div></ha-card>
    `;
  }

  set hass(hass) {
    this._hass = hass;
    try {
      this._zeichne();
    } catch (e) {
      this._zeigeFehler("hass", e);
    }
  }

  _zeigeFehler(wo, e) {
    const text = "DVB-Tafel " + VERSION + ", Fehler in " + wo + ": " +
      (e && e.message ? e.message : String(e));
    console.error(text, e);
    try {
      if (!this.shadowRoot) { this.attachShadow({ mode: "open" }); }
      const ziel = this.shadowRoot.getElementById("inhalt");
      const html = `<div style="padding:12px;color:var(--error-color,#c00)">` +
                   `${this._escape(text)}</div>`;
      if (ziel) { ziel.innerHTML = html; }
      else { this.shadowRoot.innerHTML = `<ha-card>${html}</ha-card>`; }
    } catch (_) { /* dann bleibt wenigstens die Konsole */ }
  }

  getCardSize() {
    // Auch das fragt Home Assistant unter Umstaenden vor dem ersten `hass`.
    if (!this._hass) return 3;
    return 3 + this._haltestellen().length * 2;
  }

  _haltestellen() {
    if (!this._hass) return [];
    if (this._config.entities && this._config.entities.length) {
      return this._config.entities.filter((e) => this._hass.states[e]);
    }
    // Erkennungsmerkmal ist das Attribut haltestelle_id - es gibt nur diese
    // Integration, die es setzt.
    return Object.keys(this._hass.states)
      .filter((id) => id.startsWith("sensor.") &&
                      this._hass.states[id].attributes.haltestelle_id)
      .sort();
  }

  // Die Umgebungstafel des ANGEMELDETEN Benutzers, falls er unterwegs ist.
  // Abschaltbar je Karte mit `naehe: false` - etwa auf einem Wandpanel,
  // das ohnehin nie unterwegs ist.
  _naehe() {
    if (!this._hass || this._config.naehe === false) return null;
    const benutzer = this._hass.user && this._hass.user.name;
    if (!benutzer) return null;
    const id = Object.keys(this._hass.states).find((i) =>
      i.startsWith("sensor.") && this._hass.states[i].attributes.dvb_naehe);
    if (!id) return null;
    const a = this._hass.states[id].attributes;
    const n = (a.unterwegs || {})[benutzer];
    if (!n || !(n.haltestellen || []).length) return null;
    return { ...n, benutzer, zeitfenster: a.zeitfenster,
             anzeigen: a.anzeigen, abgerufen: a.abgerufen };
  }

  _fussweg(attr) {
    const wege = attr.fusswege || {};
    // Fester Ausgangspunkt je Karte, z. B. `fussweg_von: Zuhause` auf einem
    // Wandpanel: das haengt zu Hause, egal wer gerade angemeldet ist.
    const fest = this._config.fussweg_von;
    if (fest && wege[fest]) return { ...wege[fest], quelle: fest };
    const benutzer = this._hass.user && this._hass.user.name;
    // Erst der angemeldete Benutzer, dann Zuhause. Steht der Benutzer nicht
    // in der Liste (kein Standort freigegeben), ist Zuhause die ehrlichste
    // Annahme - und die Karte sagt auch dazu, von wo gerechnet wurde.
    if (benutzer && wege[benutzer]) return { ...wege[benutzer], quelle: benutzer };
    if (wege["Zuhause"]) return { ...wege["Zuhause"], quelle: "Zuhause" };
    return null;
  }

  _zeichne() {
    if (!this.shadowRoot) return;
    // hass kann NOCH FEHLEN. Home Assistant ruft je nach Ansicht erst
    // setConfig und dann `hass` auf - und setConfig zeichnet bereits. Ohne
    // diese Zeile greift _haltestellen() auf this._hass.states zu, wirft
    // einen TypeError, und die Karte zeigt "Konfigurationsfehler".
    // Aufgefallen auf dem Wandpanel-Dashboard; auf dem Hauptdashboard war
    // die Reihenfolge zufaellig umgekehrt und der Fehler blieb verborgen.
    if (!this._hass) return;
    const ziel = this.shadowRoot.getElementById("inhalt");
    const stellen = this._haltestellen();
    const naehe = this._naehe();
    if (!stellen.length && !naehe) {
      ziel.innerHTML = `<div class="leer">Keine Haltestelle eingerichtet.</div>`;
      return;
    }

    let html = "";
    let stand = null;

    // Unterwegs zuerst die Haltestellen um den eigenen Standort - die
    // eingestellten (meist die von zu Hause) sind dann weit weg und stehen
    // darunter. Alles laeuft durch dieselbe Zeichenschleife, damit beide
    // gleich aussehen.
    const eintraege = [];
    if (naehe) {
      stand = naehe.abgerufen || stand;
      naehe.haltestellen.forEach((t, i) => eintraege.push({
        titel: t.haltestelle,
        a: { ...t, zeitfenster: naehe.zeitfenster, anzeigen: naehe.anzeigen },
        weg: t.weg,
        kurz: true,
        bereich: i === 0 ? "In deiner Nähe · ab " +
          (naehe.adresse || "deinem Standort") : null,
      }));
    }
    stellen.forEach((id, i) => {
      const z = this._hass.states[id];
      eintraege.push({
        titel: z.attributes.haltestelle || z.entity_id,
        a: z.attributes,
        weg: this._fussweg(z.attributes),
        kurz: false,
        bereich: naehe && i === 0 ? "Eingestellte Haltestellen" : null,
      });
    });

    for (const e of eintraege) {
      const a = e.a;
      const weg = e.weg;
      stand = a.abgerufen || stand;
      if (e.bereich) {
        html += `<div class="bereich">${this._escape(e.bereich)}</div>`;
      }

      html += `<div class="halt"><div class="kopf">
        <span class="name">${this._escape(e.titel)}</span>
        <span class="weg">${a.zeitfenster ? `nächste ${a.zeitfenster} Min. · ` : ""}${weg
          ? `${weg.minuten} Min. zu Fuß · ${weg.meter} m`
            + (e.kurz ? "" : " ab " + this._escape(weg.adresse || weg.quelle))
          : "Fußweg unbekannt"}</span>
      </div>`;

      // Nur noch, was zu schaffen ist (Nutzerentscheidung 2026-09-10). Die
      // Erreichbarkeit wird HIER bestimmt und nicht aus dem Attribut
      // uebernommen: das ist vom Server aus EINEM Standort gerechnet, hier
      // zaehlt der des angemeldeten Benutzers.
      const alle = a.abfahrten || [];
      let fahrten = weg
        ? alle.filter((f) => f.faellt_aus || f.minuten >= weg.minuten)
        : alle;
      // Zwei Betriebsarten: feste Zeilenzahl oder alles im Zeitfenster.
      if (a.zeitfenster) {
        fahrten = fahrten.filter((f) => f.minuten <= a.zeitfenster);
      } else {
        fahrten = fahrten.slice(0, a.anzeigen || 8);
      }
      // Hoechstzahl je Karte - ein Wandpanel ohne Scrollen hat ein festes
      // Hoehenbudget, auch im Zeitfenster-Betrieb.
      if (this._config.max_zeilen) {
        fahrten = fahrten.slice(0, this._config.max_zeilen);
      }

      if (!alle.length) {
        html += `<div class="leer">keine Abfahrten</div>`;
      } else if (!fahrten.length) {
        html += `<div class="leer">`
          + (a.zeitfenster
            ? `keine erreichbare Abfahrt in den nächsten ${a.zeitfenster} Minuten`
            : "keine Abfahrt zu Fuß erreichbar")
          + (weg ? ` (${weg.minuten} Min. Weg, nächste in ${alle[0].minuten} Min.)` : "")
          + `</div>`;
      }
      for (const f of fahrten) {
        const [hg, vg] = FARBEN[f.verkehrsmittel] || ["#6b7280", "#ffffff"];
        let ab;
        if (f.faellt_aus) {
          ab = `<span class="aus">fällt aus</span>`;
        } else {
          ab = f.minuten === 0 ? "jetzt" : `${f.minuten} min`;
          if (f.verspaetung > 0) {
            ab += ` <span class="verspaetet">+${f.verspaetung}</span>`;
          }
        }
        // Zusatzangaben - jede nur, wenn sie etwas hergibt.
        const dazu = [];
        if (f.steig) {
          dazu.push(`<span class="steig">${this._escape(f.steig_art || "Steig")} `
            + `${this._escape(f.steig)}</span>`);
        }
        // Nur die Verspaetung, nicht die Planzeit: dass die Bahn um 00:18
        // haette kommen sollen, hilft niemandem mehr, der auf sie wartet.
        if (f.verspaetung > 0 && !f.faellt_aus) {
          dazu.push(`<span class="verspaetet">${f.verspaetung} Min. später</span>`);
        }
        // Bleibt leer, solange der VVO die Auslastung nicht befuellt.
        if (f.auslastung) { dazu.push(this._escape(f.auslastung)); }

        html += `<div class="zeile">
          <span class="linie" style="background:${hg};color:${vg}">${this._escape(f.linie)}</span>
          <span class="ziel">${this._escape(f.ziel)}</span>
          <span class="ab">${ab}</span>
          ${dazu.length ? `<span class="dazu">${dazu.join(" · ")}</span>` : ""}
        </div>`;
      }
      html += `</div>`;
    }
    ziel.innerHTML = html;
    this.shadowRoot.getElementById("fuss").textContent =
      stand ? `Stand ${new Date(stand).toLocaleTimeString("de-DE",
        { hour: "2-digit", minute: "2-digit" })}` : "";
  }

  _escape(wert) {
    return String(wert === undefined || wert === null ? "" : wert)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

// Die Datei kann jetzt auf ZWEI Wegen ins Frontend kommen (extra_module_url
// und Lovelace-Ressource). Ein zweites define wuerde werfen - also erst
// nachsehen. Das Element ist in beiden Faellen dasselbe.
if (!customElements.get("dvb-tafel-card")) {
  customElements.define("dvb-tafel-card", DvbTafelCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "dvb-tafel-card",
  name: "DVB Abfahrtstafel",
  description: "Abfahrten der Dresdner Verkehrsbetriebe mit Fußweg zur Haltestelle",
});
