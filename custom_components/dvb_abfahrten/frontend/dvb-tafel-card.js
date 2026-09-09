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

class DvbTafelCard extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
    this._aufbauen();
    this._zeichne();
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
    this._zeichne();
  }

  getCardSize() {
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

  _fussweg(attr) {
    const wege = attr.fusswege || {};
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
    const ziel = this.shadowRoot.getElementById("inhalt");
    const stellen = this._haltestellen();
    if (!stellen.length) {
      ziel.innerHTML = `<div class="leer">Keine Haltestelle eingerichtet.</div>`;
      return;
    }

    let html = "";
    let stand = null;
    for (const id of stellen) {
      const z = this._hass.states[id];
      const a = z.attributes;
      const weg = this._fussweg(a);
      stand = a.abgerufen || stand;

      html += `<div class="halt"><div class="kopf">
        <span class="name">${this._escape(a.haltestelle || z.entity_id)}</span>
        <span class="weg">${a.zeitfenster ? `nächste ${a.zeitfenster} Min. · ` : ""}${weg
          ? `${weg.minuten} Min. zu Fuß · ${weg.meter} m ab `
            + this._escape(weg.adresse || weg.quelle)
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

customElements.define("dvb-tafel-card", DvbTafelCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "dvb-tafel-card",
  name: "DVB Abfahrtstafel",
  description: "Abfahrten der Dresdner Verkehrsbetriebe mit Fußweg zur Haltestelle",
});
