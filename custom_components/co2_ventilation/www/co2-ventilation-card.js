/* CO2 Ventilation card \u2014 ships with the co2_ventilation integration. */

const CARD_VERSION = "0.2.2";
const PLATFORM = "co2_ventilation";
const COLORS = ["#3987e5", "#1baf7a", "#eda100", "#eb6834", "#9085e9", "#e87ba4", "#008300", "#e66767"];
const STATUS_TEXT = {
  starting: "Starting up",
  disabled: "Auto off",
  idle: "Idle",
  ventilating: "Ventilating",
  min_run_hold: "Finishing minimum run",
  manual: "Fan on manually",
  no_data: "No sensor data",
};
const STATUS_TONE = {
  ventilating: "on",
  min_run_hold: "on",
  manual: "on",
  disabled: "muted",
  starting: "muted",
  no_data: "warn",
  idle: "ok",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class Co2VentilationCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._history = null;
    this._historyAt = 0;
    this._dragging = false;
    this._built = false;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { hours: 24, show_chart: true, ...config };
    this._built = false;
    this._history = null;
    this._historyAt = 0;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config || this._dragging) return;
    this._render();
    if (this._config.show_chart && Date.now() - this._historyAt > 5 * 60 * 1000) {
      this._historyAt = Date.now();
      this._loadHistory();
    }
  }

  getCardSize() {
    return this._config?.show_chart === false ? 5 : 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ---------- entity discovery ----------

  _entities() {
    const hass = this._hass;
    const reg = Object.values(hass.entities || {}).filter((e) => e.platform === PLATFORM);
    let status = this._config.entity;
    if (!status) status = reg.find((e) => e.translation_key === "status")?.entity_id;
    if (!status) status = Object.keys(hass.states).find((id) => id.startsWith("sensor.") && hass.states[id].attributes?.fan_entity && hass.states[id].attributes?.co2_sensors);
    if (!status || !hass.states[status]) return null;

    const device = hass.entities?.[status]?.device_id;
    const mine = reg.filter((e) => !device || e.device_id === device);
    const byKey = (key, fallbackSuffix) =>
      mine.find((e) => e.translation_key === key)?.entity_id ||
      Object.keys(hass.states).find((id) => id.endsWith(fallbackSuffix) && id.split(".")[1].startsWith(status.split(".")[1].replace(/_status$/, "")));

    const attrs = hass.states[status].attributes;
    const sensors = this._config.sensors || [...(attrs.co2_sensors || []), ...(this._config.extra_sensors || [])];
    return {
      status,
      fan: attrs.fan_entity,
      sensors,
      auto: byKey("auto", "_auto_ventilation"),
      on: byKey("on_setpoint", "_fan_on_at"),
      off: byKey("off_setpoint", "_fan_off_at"),
      min: byKey("min_run", "_minimum_run_time"),
      highest: byKey("highest_co2", "_highest_co2"),
    };
  }

  _num(id, fallback = null) {
    const v = parseFloat(this._hass.states[id]?.state);
    return Number.isFinite(v) ? v : fallback;
  }

  _name(id) {
    const st = this._hass.states[id];
    let n = st?.attributes?.friendly_name || id;
    return n.replace(/\s*(carbon dioxide|co2|co\u2082)\s*$/i, "").replace(/\s*(carbon dioxide|co2|co\u2082)\s*/gi, " ").trim() || n;
  }

  // ---------- actions ----------

  _toast(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      this._toast(err?.message || String(err));
      this._render(true);
    }
  }

  // ---------- history ----------

  async _loadHistory() {
    const e = this._entities();
    if (!e) return;
    const ids = [...new Set([...e.sensors, e.fan].filter(Boolean))];
    const end = new Date();
    const start = new Date(end.getTime() - this._config.hours * 3600 * 1000);
    try {
      const res = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      const out = {};
      for (const id of ids) {
        out[id] = (res[id] || []).map((p) => ({
          t: (p.lu ?? p.lc ?? Date.parse(p.last_updated || p.last_changed) / 1000) * 1000,
          s: p.s ?? p.state,
        }));
      }
      this._history = { start: start.getTime(), end: end.getTime(), data: out };
    } catch (err) {
      this._history = { error: err?.message || "History unavailable" };
    }
    this._renderChart();
  }

  // ---------- render ----------

  _render(force = false) {
    if (!this._config || !this._hass) return;
    const e = this._entities();
    if (!e) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">CO2 Ventilation isn't set up yet. Add the integration under Settings \u2192 Devices &amp; services.</div></ha-card>`;
      this._built = false;
      return;
    }
    this._e = e;
    if (!this._built || force) this._build();
    this._update();
  }

  _build() {
    const e = this._e;
    this.shadowRoot.innerHTML = `
<style>
  :host { --ok:#0ca30c; --warn:#e8a200; --bad:#d03b3b; }
  ha-card { padding: 16px; }
  .head { display:flex; align-items:center; gap:12px; margin-bottom:14px; }
  .title { font-size:18px; font-weight:500; flex:1; color:var(--primary-text-color); }
  .pill { font-size:12px; padding:4px 10px; border-radius:999px; white-space:nowrap; }
  .pill.on { background:rgba(237,161,0,.18); color:var(--warning-color,#b37500); }
  .pill.ok { background:rgba(12,163,12,.14); color:var(--success-color,#0a7d0a); }
  .pill.warn { background:rgba(208,59,59,.14); color:var(--error-color,#b02a2a); }
  .pill.muted { background:var(--secondary-background-color); color:var(--secondary-text-color); }
  .rooms { display:grid; grid-template-columns:repeat(auto-fill,minmax(110px,1fr)); gap:8px; margin-bottom:14px; }
  .room { background:var(--secondary-background-color); border-radius:12px; padding:10px 12px; cursor:pointer; }
  .room .n { font-size:12px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:flex; align-items:center; gap:6px; }
  .room .dot { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
  .room .v { font-size:20px; font-weight:500; color:var(--primary-text-color); margin-top:2px; }
  .room .v small { font-size:11px; color:var(--secondary-text-color); font-weight:400; }
  .bar { height:5px; border-radius:3px; background:var(--divider-color); margin-top:6px; overflow:hidden; }
  .bar span { display:block; height:100%; border-radius:3px; transition:width .3s; }
  .ctl { border-top:1px solid var(--divider-color); padding-top:6px; }
  .row { display:flex; align-items:center; gap:10px; min-height:40px; }
  .row ha-icon { color:var(--secondary-text-color); --mdc-icon-size:20px; }
  .row .l { flex:0 0 108px; font-size:14px; color:var(--primary-text-color); }
  .row .grow { flex:1; }
  .row input[type=range] { flex:1; accent-color:var(--primary-color); min-width:60px; }
  .row .val { min-width:64px; text-align:right; font-size:13px; color:var(--secondary-text-color); font-variant-numeric:tabular-nums; }
  .tg { width:40px; height:22px; border-radius:11px; border:none; position:relative; cursor:pointer; padding:0; flex-shrink:0; background:var(--disabled-color,#9e9e9e); transition:background .15s; }
  .tg::after { content:""; position:absolute; top:3px; left:3px; width:16px; height:16px; border-radius:50%; background:#fff; transition:left .15s; }
  .tg.on { background:var(--primary-color); }
  .tg.on::after { left:21px; }
  .sub { font-size:12px; color:var(--secondary-text-color); }
  .chart { margin-top:12px; border-top:1px solid var(--divider-color); padding-top:10px; }
  .legend { display:flex; flex-wrap:wrap; gap:4px 12px; font-size:12px; color:var(--secondary-text-color); margin-bottom:4px; }
  .legend span { display:flex; align-items:center; gap:4px; }
  .legend i { width:10px; height:10px; border-radius:2px; display:inline-block; }
  svg text { font-size:11px; fill:var(--secondary-text-color); font-family:inherit; }
</style>
<ha-card>
  <div class="head">
    <div class="title">${esc(this._config.title || "CO\u2082 ventilation")}</div>
    <span class="pill" id="status"></span>
  </div>
  <div class="rooms" id="rooms"></div>
  <div class="ctl">
    <div class="row"><ha-icon icon="mdi:robot"></ha-icon><span class="l">Auto</span><span class="grow sub" id="autosub"></span><button class="tg" id="auto" aria-label="Auto ventilation"></button></div>
    <div class="row"><ha-icon icon="mdi:fan"></ha-icon><span class="l">HVAC fan</span><span class="grow sub" id="fansub"></span><button class="tg" id="fan" aria-label="HVAC fan"></button></div>
    ${this._sliderRow("on", "mdi:arrow-collapse-up", "Fan on at", e.on)}
    ${this._sliderRow("off", "mdi:arrow-collapse-down", "Fan off at", e.off)}
    ${this._sliderRow("min", "mdi:timer-outline", "Minimum run", e.min)}
  </div>
  ${this._config.show_chart ? `<div class="chart"><div class="legend" id="legend"></div><div id="svg"></div></div>` : ""}
</ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("auto").addEventListener("click", () => e.auto && this._call("switch", "toggle", { entity_id: e.auto }));
    $("fan").addEventListener("click", () => e.fan && this._call("homeassistant", "toggle", { entity_id: e.fan }));
    for (const key of ["on", "off", "min"]) {
      const input = $(`s_${key}`);
      if (!input) continue;
      const unit = key === "min" ? " min" : " ppm";
      input.addEventListener("pointerdown", () => (this._dragging = true));
      input.addEventListener("input", () => {
        this._dragging = true;
        $(`v_${key}`).textContent = `${input.value}${unit}`;
      });
      input.addEventListener("change", async () => {
        this._dragging = false;
        await this._call("number", "set_value", { entity_id: e[key], value: Number(input.value) });
      });
      input.addEventListener("blur", () => (this._dragging = false));
    }
    this._built = true;
    this._renderChart();
  }

  _sliderRow(key, icon, label, entityId) {
    if (!entityId) return "";
    const a = this._hass.states[entityId]?.attributes || {};
    return `<div class="row"><ha-icon icon="${icon}"></ha-icon><span class="l">${label}</span>
      <input type="range" id="s_${key}" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
      <span class="val" id="v_${key}"></span></div>`;
  }

  _update() {
    const e = this._e;
    const hass = this._hass;
    const $ = (id) => this.shadowRoot.getElementById(id);
    const on = this._num(e.on, 900);
    const off = this._num(e.off, 700);

    const st = hass.states[e.status]?.state;
    const pill = $("status");
    pill.textContent = STATUS_TEXT[st] || st || "";
    pill.className = `pill ${STATUS_TONE[st] || "muted"}`;

    const rooms = e.sensors
      .map((id, i) => {
        const v = this._num(id);
        const pct = v == null ? 0 : Math.max(4, Math.min(100, ((v - 400) / (Math.max(on * 1.4, 1200) - 400)) * 100));
        const tone = v == null ? "var(--disabled-color)" : v >= on ? "var(--bad)" : v >= off ? "var(--warn)" : "var(--ok)";
        return `<div class="room" data-id="${esc(id)}"><div class="n"><span class="dot" style="background:${COLORS[i % COLORS.length]}"></span>${esc(this._name(id))}</div>
        <div class="v">${v == null ? "\u2014" : Math.round(v)} <small>ppm</small></div>
        <div class="bar"><span style="width:${pct}%;background:${tone}"></span></div></div>`;
      })
      .join("");
    const roomsEl = $("rooms");
    if (roomsEl.innerHTML !== rooms) {
      roomsEl.innerHTML = rooms;
      roomsEl.querySelectorAll(".room").forEach((el) => el.addEventListener("click", () => this._moreInfo(el.dataset.id)));
    }

    const autoOn = hass.states[e.auto]?.state === "on";
    $("auto").classList.toggle("on", autoOn);
    $("autosub").textContent = autoOn ? "" : "Fan won't change on its own";
    const fanOn = hass.states[e.fan]?.state === "on";
    $("fan").classList.toggle("on", fanOn);
    const remaining = hass.states[e.status]?.attributes?.min_run_remaining_s || 0;
    $("fansub").textContent = st === "min_run_hold" && remaining ? `${Math.ceil(remaining / 60)} min left` : fanOn ? "Running" : "Off";

    for (const key of ["on", "off", "min"]) {
      const input = $(`s_${key}`);
      if (!input || !e[key]) continue;
      const v = this._num(e[key]);
      if (v == null) continue;
      input.value = v;
      $(`v_${key}`).textContent = `${Math.round(v)}${key === "min" ? " min" : " ppm"}`;
    }

    const legend = $("legend");
    if (legend) {
      const html =
        e.sensors.map((id, i) => `<span><i style="background:${COLORS[i % COLORS.length]}"></i>${esc(this._name(id))}</span>`).join("") +
        `<span><i style="background:rgba(237,161,0,.35)"></i>Fan on</span>`;
      if (legend.innerHTML !== html) legend.innerHTML = html;
    }
    const key = `${on}|${off}|${this._history?.end}`;
    if (key !== this._chartKey || Date.now() - (this._chartAt || 0) > 60000) {
      this._chartKey = key;
      this._chartAt = Date.now();
      this._renderChart();
    }
  }

  _renderChart() {
    const box = this.shadowRoot.getElementById("svg");
    if (!box) return;
    const h = this._history;
    if (!h) {
      box.innerHTML = `<div class="sub" style="padding:24px 0;text-align:center">Loading history\u2026</div>`;
      return;
    }
    if (h.error) {
      box.innerHTML = `<div class="sub" style="padding:24px 0;text-align:center">${esc(h.error)}</div>`;
      return;
    }
    const e = this._e;
    const W = 600, H = 220, L = 40, R = 8, T = 8, B = 22;
    const on = this._num(e.on, 900), off = this._num(e.off, 700);
    const end = Date.now();
    const start = end - this._config.hours * 3600 * 1000;
    const x = (t) => L + ((t - start) / (end - start)) * (W - L - R);

    // 5-minute bucket averages, carrying the last value forward.
    const step = 5 * 60 * 1000;
    const series = e.sensors.map((id) => {
      const pts = (h.data[id] || []).map((p) => ({ t: p.t, v: parseFloat(p.s) })).filter((p) => Number.isFinite(p.v));
      const out = [];
      let j = 0, last = null;
      for (let t = start; t <= end; t += step) {
        let sum = 0, n = 0;
        while (j < pts.length && pts[j].t < t + step) {
          if (pts[j].t >= t) { sum += pts[j].v; n++; }
          last = pts[j].v; j++;
        }
        const v = n ? sum / n : last;
        if (v != null && t + step > (pts[0]?.t ?? Infinity)) out.push([t + step / 2, v]);
      }
      const now = this._num(id);
      if (now != null) out.push([end, now]);
      return out;
    });
    let maxV = Math.max(on + 100, 1000);
    for (const s of series) for (const [, v] of s) maxV = Math.max(maxV, v);
    maxV = Math.ceil(maxV / 100) * 100;
    const minV = 400;
    const y = (v) => T + (1 - (Math.max(minV, v) - minV) / (maxV - minV)) * (H - T - B);

    let svg = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="CO2 by room over the last ${this._config.hours} hours with fan run time shaded">`;

    // fan on spans
    const fanPts = (h.data[e.fan] || []).filter((p) => p.s === "on" || p.s === "off");
    for (let i = 0; i < fanPts.length; i++) {
      if (fanPts[i].s !== "on") continue;
      const a = Math.max(fanPts[i].t, start);
      const b = i + 1 < fanPts.length ? fanPts[i + 1].t : end;
      svg += `<rect x="${x(a).toFixed(1)}" y="${T}" width="${Math.max(1, x(b) - x(a)).toFixed(1)}" height="${H - T - B}" fill="rgba(237,161,0,0.18)"/>`;
    }
    if (this._hass.states[e.fan]?.state === "on" && !fanPts.length) {
      svg += `<rect x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="rgba(237,161,0,0.18)"/>`;
    }

    // grid
    for (let v = minV; v <= maxV; v += 200) {
      svg += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--divider-color)" stroke-width="1"/>`;
      svg += `<text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`;
    }
    const hourMs = 3600 * 1000;
    const tickEvery = this._config.hours > 12 ? 4 : 2;
    const first = new Date(start);
    first.setMinutes(0, 0, 0);
    for (let t = first.getTime() + hourMs; t < end; t += hourMs) {
      const d = new Date(t);
      if (d.getHours() % tickEvery) continue;
      const label = d.getHours() === 0 ? d.toLocaleDateString([], { month: "short", day: "numeric" }) : d.toLocaleTimeString([], { hour: "numeric" });
      svg += `<text x="${x(t)}" y="${H - 6}" text-anchor="middle">${esc(label)}</text>`;
    }

    // setpoints
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(on)}" y2="${y(on)}" stroke="#d03b3b" stroke-dasharray="5 4" stroke-width="1.5"/>`;
    svg += `<line x1="${L}" x2="${W - R}" y1="${y(off)}" y2="${y(off)}" stroke="#0ca30c" stroke-dasharray="5 4" stroke-width="1.5"/>`;
    svg += `<text x="${W - R - 2}" y="${y(on) - 4}" text-anchor="end" style="fill:#d03b3b">On ${Math.round(on)}</text>`;
    svg += `<text x="${W - R - 2}" y="${y(off) + 13}" text-anchor="end" style="fill:#0ca30c">Off ${Math.round(off)}</text>`;

    // lines
    series.forEach((s, i) => {
      if (s.length < 2) return;
      const d = s.map(([t, v], k) => `${k ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join("");
      svg += `<path d="${d}" fill="none" stroke="${COLORS[i % COLORS.length]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    });
    svg += `</svg>`;
    box.innerHTML = svg;
  }
}

if (!customElements.get("co2-ventilation-card")) {
  customElements.define("co2-ventilation-card", Co2VentilationCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "co2-ventilation-card",
    name: "CO2 Ventilation",
    description: "Room CO2, fan control, setpoint sliders, and a 24-hour chart.",
    preview: true,
    documentationURL: "https://github.com/stephencorrell-ops/ha-co2-ventilation",
  });
  console.info(`%c CO2-VENTILATION-CARD %c ${CARD_VERSION} `, "background:#1baf7a;color:#fff", "");
}
