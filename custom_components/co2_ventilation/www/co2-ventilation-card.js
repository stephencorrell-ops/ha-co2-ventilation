/* CO2 Ventilation card \u2014 ships with the co2_ventilation integration. */
(() => {

const CARD_VERSION = "0.7.0";
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
const SPEED_LABELS = { low: "Low", medium_low: "Med-low", medium: "Medium" };
const SPEED_LEVEL = { low: 1, medium_low: 2, medium: 3 };
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
    return { columns: "full", rows: "auto" };
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
      speed: byKey("speed", "_ventilation_speed"),
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
  .setpts.locked input[type=range] { pointer-events:none; opacity:.4; }
  .val { display:flex; align-items:center; justify-content:flex-end; gap:4px; }
  .val input { width:58px; box-sizing:border-box; text-align:right; font:inherit; font-size:14px; color:var(--primary-text-color); background:var(--secondary-background-color); border:1px solid var(--divider-color); border-radius:6px; padding:4px 6px; -moz-appearance:textfield; }
  .val input::-webkit-outer-spin-button, .val input::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
  .val input:focus { outline:none; border-color:var(--primary-color); }
  .setpts.locked .val input { background:transparent; border-color:transparent; color:var(--secondary-text-color); padding-right:0; }
  .lock { border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color); border-radius:16px; padding:4px 12px; font:inherit; font-size:13px; cursor:pointer; display:flex; align-items:center; gap:6px; }
  .lock ha-icon { --mdc-icon-size:18px; color:inherit; }
  .setpts:not(.locked) .lock { border-color:var(--primary-color); color:var(--primary-color); }
  .seg { display:flex; gap:4px; flex:1; justify-content:flex-end; }
  .seg button { border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color); border-radius:16px; padding:4px 12px; font:inherit; font-size:13px; cursor:pointer; }
  .seg button.on { background:var(--primary-color); border-color:var(--primary-color); color:var(--text-primary-color,#fff); }
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
    ${e.speed ? `<div class="row"><ha-icon icon="mdi:fan-speed-1" id="speedicon"></ha-icon><span class="l">Speed</span><div class="seg" id="speed" role="group" aria-label="Ventilation speed">${(this._hass.states[e.speed]?.attributes?.options || Object.keys(SPEED_LABELS)).map((o) => `<button data-o="${esc(o)}">${esc(SPEED_LABELS[o] || o)}</button>`).join("")}</div></div>` : ""}
    <div class="setpts locked" id="setpts">
      <div class="row"><ha-icon icon="mdi:tune-variant"></ha-icon><span class="l">Setpoints</span><span class="grow sub" id="locksub">Locked</span>
        <button class="lock" id="lock" aria-label="Unlock setpoints"><ha-icon icon="mdi:lock"></ha-icon><span id="locktxt">Unlock</span></button></div>
      ${this._sliderRow("on", "mdi:arrow-collapse-up", "Fan on at", e.on)}
      ${this._sliderRow("off", "mdi:arrow-collapse-down", "Fan off at", e.off)}
      ${this._sliderRow("min", "mdi:timer-outline", "Minimum run", e.min)}
    </div>
  </div>
  ${this._config.show_chart ? `<div class="chart"><div class="legend" id="legend"></div><div id="svg"></div></div>` : ""}
</ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("auto").addEventListener("click", () => e.auto && this._call("switch", "toggle", { entity_id: e.auto }));
    $("fan").addEventListener("click", () => {
      if (!e.fan) return;
      const pct = this._speedPercentage();
      if (this._hass.states[e.fan]?.state !== "on" && pct != null) {
        this._call("fan", "turn_on", { entity_id: e.fan, percentage: pct });
      } else {
        this._call("homeassistant", "toggle", { entity_id: e.fan });
      }
    });
    $("speed")?.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => this._call("select", "select_option", { entity_id: e.speed, option: b.dataset.o }))
    );
    $("lock").addEventListener("click", () => this._setLocked(!this._locked));
    this._setLocked(true);
    for (const key of ["on", "off", "min"]) {
      const input = $(`s_${key}`);
      if (!input) continue;
      const unit = key === "min" ? " min" : " ppm";
      input.addEventListener("pointerdown", () => {
        this._dragging = true;
        this._armRelock();
      });
      input.addEventListener("input", () => {
        this._dragging = true;
        $(`v_${key}`).value = input.value;
      });
      input.addEventListener("change", async () => {
        this._dragging = false;
        if (this._locked) {
          this._render(true);
          return;
        }
        this._armRelock(10);
        await this._call("number", "set_value", { entity_id: e[key], value: Number(input.value) });
      });
      const box = $(`v_${key}`);
      box.addEventListener("focus", () => {
        this._armRelock(60);
        box.select();
      });
      box.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") box.blur();
        if (ev.key === "Escape") {
          box.value = Math.round(this._num(e[key]));
          box.blur();
        }
      });
      box.addEventListener("change", async () => {
        if (this._locked) return this._render(true);
        const lo = Number(input.min), hi = Number(input.max), step = Number(input.step) || 1;
        let v = Number(box.value);
        if (!Number.isFinite(v) || box.value === "") {
          box.value = Math.round(this._num(e[key]));
          return;
        }
        v = Math.min(hi, Math.max(lo, Math.round(v / step) * step));
        box.value = v;
        input.value = v;
        this._armRelock(10);
        await this._call("number", "set_value", { entity_id: e[key], value: v });
      });
      input.addEventListener("blur", () => (this._dragging = false));
    }
    this._built = true;
    this._renderChart();
  }

  // Same math as the integration: speed N of the fan's steps, as a percentage.
  _speedPercentage() {
    const e = this._e;
    if (!e?.speed || !e.fan?.startsWith("fan.")) return null;
    const step = parseFloat(this._hass.states[e.fan]?.attributes?.percentage_step);
    if (!Number.isFinite(step) || step <= 0 || step >= 100) return null;
    const count = Math.max(1, Math.round(100 / step));
    if (count <= 1) return null;
    const level = Math.min(SPEED_LEVEL[this._hass.states[e.speed]?.state] || 1, count);
    return Math.floor((level * 100) / count);
  }

  _setLocked(locked) {
    this._locked = locked;
    clearTimeout(this._relockTimer);
    const $ = (id) => this.shadowRoot.getElementById(id);
    const box = $("setpts");
    if (!box) return;
    box.classList.toggle("locked", locked);
    box.querySelectorAll("input").forEach((i) => (i.disabled = locked));
    $("lock").querySelector("ha-icon").setAttribute("icon", locked ? "mdi:lock" : "mdi:lock-open-variant");
    $("lock").setAttribute("aria-label", locked ? "Unlock setpoints" : "Lock setpoints");
    $("locktxt").textContent = locked ? "Unlock" : "Lock";
    $("locksub").textContent = locked ? "Locked" : "Unlocked \u2014 locks again in 30 s";
    if (!locked) this._armRelock();
  }

  _armRelock(seconds = 30) {
    if (this._locked) return;
    clearTimeout(this._relockTimer);
    const sub = this.shadowRoot.getElementById("locksub");
    if (sub) sub.textContent = `Unlocked \u2014 locks again in ${seconds} s`;
    this._relockTimer = setTimeout(() => {
      this._dragging = false;
      this._setLocked(true);
    }, seconds * 1000);
  }

  _sliderRow(key, icon, label, entityId) {
    if (!entityId) return "";
    const a = this._hass.states[entityId]?.attributes || {};
    return `<div class="row"><ha-icon icon="${icon}"></ha-icon><span class="l">${label}</span>
      <input type="range" id="s_${key}" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}">
      <span class="val"><input type="number" id="v_${key}" inputmode="numeric" min="${a.min ?? 0}" max="${a.max ?? 100}" step="${a.step ?? 1}" aria-label="${label}"><span>${key === "min" ? "min" : "ppm"}</span></span></div>`;
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
    const speedEl = $("speed");
    if (speedEl) {
      const cur = hass.states[e.speed]?.state;
      speedEl.querySelectorAll("button").forEach((b) => {
        b.classList.toggle("on", b.dataset.o === cur);
        b.setAttribute("aria-pressed", b.dataset.o === cur ? "true" : "false");
      });
      $("speedicon")?.setAttribute("icon", `mdi:fan-speed-${SPEED_LEVEL[cur] || 1}`);
    }

    for (const key of ["on", "off", "min"]) {
      const input = $(`s_${key}`);
      if (!input || !e[key]) continue;
      const v = this._num(e[key]);
      if (v == null) continue;
      input.value = v;
      const box = $(`v_${key}`);
      if (this.shadowRoot.activeElement !== box) box.value = Math.round(v);
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
    description: "Room CO2, fan control and speed, setpoint sliders, and a 24-hour chart.",
    preview: false,
    documentationURL: "https://github.com/stephencorrell-ops/ha-co2-ventilation",
  });
  console.info(`%c CO2-VENTILATION-CARD %c ${CARD_VERSION} `, "background:#1baf7a;color:#fff", "");
}

// ======================================================================
// Thermostat history card
// ======================================================================

const MODES = ["heat", "strips", "cool", "fan", "vent"];
const MODE_COLOR = { heat: "#eb6834", strips: "#e34948", cool: "#2a78d6", fan: "#888780", vent: "#1baf7a" };
const MODE_LABEL = { heat: "Heat pump", strips: "Heat strips", cool: "Cooling", fan: "Fan only", vent: "CO₂ ventilation" };
const MODE_LANE = { heat: "Heat", strips: "Strips", cool: "Cool", fan: "Fan", vent: "Vent" };
const RANGES = [[6, "6 h"], [24, "24 h"], [168, "7 d"]];

// Decide what the system is doing from the 24 V calls (O is on in cooling).
const modesFrom = (g, y, o, w2, vent) => {
  const m = [];
  if (y && !o) m.push("heat");
  if (y && o) m.push("cool");
  if (w2) m.push("strips");
  if (g && !y && !w2) m.push("fan");
  if (vent) m.push("vent");
  return m;
};

const fmtDur = (ms) => {
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins} m`;
  const h = Math.floor(mins / 60), m = mins % 60;
  return m ? `${h} h ${m} m` : `${h} h`;
};

const localISO = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const fmtHours = (h) => {
  if (!Number.isFinite(h)) return "—";
  return h < 10 ? h.toFixed(1) : Math.round(h).toLocaleString();
};

class Co2ThermostatCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._history = null;
    this._historyAt = 0;
    this._built = false;
    this._hover = null;
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = { hours: 24, ...config };
    this._hours = this._config.hours;
    this._built = false;
    this._history = null;
    this._historyAt = 0;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._render();
    if (Date.now() - this._historyAt > 5 * 60 * 1000) {
      this._historyAt = Date.now();
      this._loadHistory();
    }
  }

  getCardSize() {
    return 12;
  }

  getGridOptions() {
    return { columns: "full", rows: "auto" };
  }

  // ---------- entities ----------

  _entities() {
    const hass = this._hass;
    const reg = Object.values(hass.entities || {}).filter((e) => e.platform === PLATFORM);
    let status = this._config.entity;
    if (!status) status = reg.find((e) => e.translation_key === "status")?.entity_id;
    if (!status) status = Object.keys(hass.states).find((id) => id.startsWith("sensor.") && hass.states[id].attributes?.thermostat && hass.states[id].attributes?.fan_entity);
    if (!status || !hass.states[status]) return null;
    const device = hass.entities?.[status]?.device_id;
    const mine = reg.filter((e) => !device || e.device_id === device);
    const byKey = (key) => mine.find((e) => e.translation_key === key)?.entity_id;
    const a = hass.states[status].attributes;
    const t = a.thermostat || {};
    return {
      status,
      t,
      climate: t.climate_entity,
      temp: t.temperature_sensor,
      hum: t.humidity_sensor,
      g: t.call_g,
      y: t.call_y,
      o: t.call_ob,
      w2: t.call_w2,
      vent: a.fan_entity,
      highest: byKey("highest_co2"),
      speed: byKey("speed"),
      on: byKey("on_setpoint"),
      off: byKey("off_setpoint"),
      filter: byKey("filter_runtime"),
      total: byKey("total_runtime"),
      reset: byKey("reset_filter"),
      fdate: byKey("filter_changed"),
    };
  }

  _on(id) {
    return !!id && this._hass.states[id]?.state === "on";
  }

  _num(id) {
    const v = parseFloat(this._hass.states[id]?.state);
    return Number.isFinite(v) ? v : null;
  }

  _attr(id, key) {
    const v = parseFloat(this._hass.states[id]?.attributes?.[key]);
    return Number.isFinite(v) ? v : null;
  }

  _tempUnit() {
    const e = this._e;
    return this._hass.states[e.temp]?.attributes?.unit_of_measurement || this._hass.config?.unit_system?.temperature || "°F";
  }

  _currentTemp() {
    const e = this._e;
    return e.temp ? this._num(e.temp) : this._attr(e.climate, "current_temperature");
  }

  _currentHum() {
    const e = this._e;
    return e.hum ? this._num(e.hum) : this._attr(e.climate, "current_humidity");
  }

  _setpointText() {
    const c = this._hass.states[this._e.climate];
    if (!c) return "";
    const a = c.attributes, u = this._tempUnit();
    if (Number.isFinite(a.target_temp_low) && Number.isFinite(a.target_temp_high)) return `Set ${a.target_temp_low}–${a.target_temp_high} ${u}`;
    if (Number.isFinite(a.temperature)) return `Set ${a.temperature} ${u}`;
    return c.state === "off" ? "Thermostat off" : "";
  }

  // ---------- actions ----------

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
    } catch (err) {
      this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message: err?.message || String(err) }, bubbles: true, composed: true }));
    }
  }

  _moreInfo(entityId) {
    if (entityId) this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  // ---------- history ----------

  async _loadHistory() {
    const e = this._entities();
    if (!e) return;
    this._e = e;
    const end = new Date();
    const start = new Date(end.getTime() - this._hours * 3600 * 1000);
    const plain = [e.g, e.y, e.o, e.w2, e.vent, e.temp, e.hum, e.highest].filter(Boolean);
    const ws = (ids, attrs) =>
      this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: ids,
        minimal_response: !attrs,
        no_attributes: !attrs,
        significant_changes_only: false,
      });
    try {
      const [res, cres] = await Promise.all([
        plain.length ? ws([...new Set(plain)], false) : {},
        e.climate ? ws([e.climate], true) : {},
      ]);
      const series = (rows) =>
        (rows || []).map((p) => ({
          t: (p.lu ?? p.lc ?? Date.parse(p.last_updated || p.last_changed) / 1000) * 1000,
          s: p.s ?? p.state,
          a: p.a ?? p.attributes,
        }));
      const data = {};
      for (const id of plain) data[id] = series(res[id]);
      const climate = series(cres[e.climate]);
      // Remember the last attributes on rows where only the state changed.
      let lastA = {};
      for (const p of climate) p.a = lastA = p.a ? { ...lastA, ...p.a } : lastA;
      this._history = { start: start.getTime(), end: end.getTime(), data, climate };
    } catch (err) {
      this._history = { error: err?.message || "History unavailable" };
    }
    this._renderChart();
  }

  // Value of a step series at time t.
  _at(points, t) {
    if (!points?.length) return null;
    let v = null;
    for (const p of points) {
      if (p.t > t) break;
      v = p;
    }
    return v ?? points[0];
  }

  _segments() {
    const h = this._history, e = this._e;
    if (!h?.data) return [];
    const ids = { g: e.g, y: e.y, o: e.o, w2: e.w2, vent: e.vent };
    const times = new Set([h.start, h.end]);
    for (const id of Object.values(ids)) for (const p of h.data[id] || []) if (p.t > h.start && p.t < h.end) times.add(p.t);
    const ts = [...times].sort((a, b) => a - b);
    const segs = [];
    const isOn = (id, t) => !!id && this._at(h.data[id], t)?.s === "on";
    for (let i = 0; i < ts.length - 1; i++) {
      const a = ts[i], b = ts[i + 1], mid = a + 1;
      const modes = modesFrom(isOn(e.g, mid), isOn(e.y, mid), isOn(e.o, mid), isOn(e.w2, mid), isOn(e.vent, mid));
      for (const m of modes) {
        const last = segs.findLast?.((s) => s.m === m) ?? [...segs].reverse().find((s) => s.m === m);
        if (last && last.b === a) last.b = b;
        else segs.push({ m, a, b });
      }
    }
    return segs;
  }

  // ---------- render ----------

  _render() {
    if (!this._config || !this._hass) return;
    const e = this._entities();
    if (!e) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">CO2 Ventilation isn't set up yet. Add the integration under Settings → Devices &amp; services.</div></ha-card>`;
      this._built = false;
      return;
    }
    this._e = e;
    if (!this._built) this._build();
    this._update();
  }

  _build() {
    const e = this._e;
    const configured = e.climate || e.g || e.y || e.w2;
    this.shadowRoot.innerHTML = `
<style>
  ha-card { padding: 16px; }
  .head { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
  .head ha-icon { color:var(--secondary-text-color); }
  .title { font-size:18px; font-weight:500; flex:1; color:var(--primary-text-color); }
  .pill { font-size:12px; padding:4px 10px; border-radius:999px; white-space:nowrap; background:var(--secondary-background-color); color:var(--secondary-text-color); }
  .calls { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }
  .chip { display:inline-flex; align-items:center; gap:6px; font-size:12px; padding:4px 10px; border-radius:999px; border:1px solid var(--divider-color); color:var(--disabled-text-color, var(--secondary-text-color)); }
  .chip b { font-weight:500; }
  .chip i { width:7px; height:7px; border-radius:50%; background:var(--divider-color); }
  .chip.on { color:var(--primary-text-color); background:var(--secondary-background-color); }
  .chip.on i { background:#1baf7a; }
  .stats { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
  .stat { background:var(--secondary-background-color); border-radius:12px; padding:10px 12px; cursor:pointer; min-width:0; }
  .stat .k { font-size:12px; color:var(--secondary-text-color); }
  .stat .v { font-size:22px; font-weight:500; color:var(--primary-text-color); font-variant-numeric:tabular-nums; }
  .stat .v small { font-size:13px; font-weight:400; color:var(--secondary-text-color); }
  .stat .s { font-size:12px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .bar { display:flex; align-items:center; justify-content:space-between; border-top:1px solid var(--divider-color); padding-top:10px; margin-bottom:4px; }
  .sub { font-size:13px; color:var(--secondary-text-color); }
  .seg { display:flex; gap:4px; }
  .seg button, .btn { border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color); border-radius:16px; padding:3px 11px; font:inherit; font-size:12px; cursor:pointer; }
  .seg button.on { background:var(--primary-color); border-color:var(--primary-color); color:var(--text-primary-color,#fff); }
  .legend { display:flex; flex-wrap:wrap; gap:4px 14px; font-size:12px; color:var(--secondary-text-color); margin:6px 0 2px; }
  .legend span { display:flex; align-items:center; gap:4px; }
  .legend i { width:10px; height:10px; border-radius:2px; display:inline-block; }
  .chart { position:relative; touch-action:pan-y; }
  .tip { position:absolute; top:0; pointer-events:none; background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:8px; padding:6px 9px; font-size:12px; color:var(--secondary-text-color); line-height:1.5; white-space:nowrap; display:none; }
  .tip b { color:var(--primary-text-color); font-weight:500; }
  .totals { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; border-top:1px solid var(--divider-color); padding-top:10px; margin-top:4px; }
  .totals div { font-size:12px; color:var(--secondary-text-color); min-width:0; }
  .totals .n { display:flex; align-items:center; gap:5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .totals .n i { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
  .totals .v { font-size:15px; font-weight:500; color:var(--primary-text-color); font-variant-numeric:tabular-nums; }
  .run { border-top:1px solid var(--divider-color); margin-top:10px; padding-top:10px; display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto; gap:8px 12px; align-items:center; }
  .run .k { font-size:12px; color:var(--secondary-text-color); display:flex; align-items:center; gap:6px; }
  .run .v { font-size:20px; font-weight:500; color:var(--primary-text-color); font-variant-numeric:tabular-nums; }
  .run .v small { font-size:13px; font-weight:400; color:var(--secondary-text-color); }
  .run .s { font-size:12px; color:var(--secondary-text-color); }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--divider-color); display:inline-block; }
  .dot.on { background:#1baf7a; }
  .btn.warn { border-color:var(--error-color,#d03b3b); color:var(--error-color,#d03b3b); }
  .btn.solid { background:var(--error-color,#d03b3b); border-color:var(--error-color,#d03b3b); color:#fff; }
  .link { background:none; border:none; padding:0; font:inherit; font-size:12px; color:var(--primary-color); cursor:pointer; }
  .panel { grid-column:1 / -1; display:none; align-items:center; flex-wrap:wrap; gap:8px; background:var(--secondary-background-color); border-radius:10px; padding:10px 12px; font-size:13px; color:var(--primary-text-color); }
  .panel.open { display:flex; }
  .panel .msg { flex:1 1 220px; }
  .panel input[type=date] { font:inherit; font-size:13px; color:var(--primary-text-color); background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:6px; padding:4px 6px; color-scheme:light dark; }
  .panel .err { flex-basis:100%; font-size:12px; color:var(--error-color,#d03b3b); }
  .note { font-size:13px; color:var(--secondary-text-color); padding:4px 0 8px; }
  svg text { font-size:11px; fill:var(--secondary-text-color); font-family:inherit; }
  @media (max-width: 480px) { .stats { grid-template-columns:1fr 1fr; } .totals { grid-template-columns:1fr 1fr; } }
</style>
<ha-card>
  <div class="head"><ha-icon icon="mdi:thermostat"></ha-icon><div class="title">${esc(this._config.title || "Thermostat")}</div><span class="pill" id="pill"></span></div>
  ${configured ? "" : `<div class="note">Pick your thermostat and its call inputs under CO2 Ventilation → Configure → Thermostat to fill in this card.</div>`}
  <div class="calls" id="calls"></div>
  <div class="stats">
    <div class="stat" id="st_temp"><div class="k">Temperature</div><div class="v" id="v_temp"></div><div class="s" id="s_temp"></div></div>
    <div class="stat" id="st_hum"><div class="k">Humidity</div><div class="v" id="v_hum"></div><div class="s" id="s_hum"></div></div>
    <div class="stat" id="st_co2"><div class="k">Highest CO₂</div><div class="v" id="v_co2"></div><div class="s" id="s_co2"></div></div>
  </div>
  <div class="bar"><span class="sub" id="rangetxt"></span><span class="seg" id="range">${RANGES.map(([h, l]) => `<button data-h="${h}">${l}</button>`).join("")}</span></div>
  <div class="legend">${MODES.map((m) => `<span><i style="background:${MODE_COLOR[m]}"></i>${MODE_LABEL[m]}</span>`).join("")}</div>
  <div class="chart" id="chart"><div id="svg"></div><div class="tip" id="tip"></div></div>
  <div class="totals" id="totals"></div>
  ${e.filter || e.total ? `<div class="run">
    <div><div class="k"><span class="dot" id="rundot"></span>Since filter change</div><div class="v" id="v_filter"></div><div class="s"><span id="s_filter"></span>${e.fdate ? ` \u00b7 <button class="link" id="editdate">Change date</button>` : ""}</div></div>
    <div><div class="k">Total fan runtime</div><div class="v" id="v_total"></div><div class="s">Since the motor was installed</div></div>
    ${e.reset ? `<button class="btn" id="reset">Reset filter</button>` : "<span></span>"}
    <div class="panel" id="confirm" role="alertdialog" aria-label="Confirm filter reset">
      <span class="msg">Reset the filter runtime to 0 h and set the last change to today?</span>
      <button class="btn" id="confirm_no">Cancel</button><button class="btn solid" id="confirm_yes">Reset</button>
    </div>
    <div class="panel" id="datepanel">
      <span class="msg">Last filter change</span>
      <input type="date" id="dateinput" aria-label="Last filter change date">
      <button class="btn" id="date_no">Cancel</button><button class="btn" id="date_yes">Save</button>
      <span class="err" id="dateerr"></span>
    </div>
  </div>` : ""}
</ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    $("range").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => {
        this._hours = Number(b.dataset.h);
        this._history = null;
        this._historyAt = Date.now();
        this._update();
        this._renderChart();
        this._loadHistory();
      })
    );
    $("st_temp").addEventListener("click", () => this._moreInfo(e.temp || e.climate));
    $("st_hum").addEventListener("click", () => this._moreInfo(e.hum || e.climate));
    $("st_co2").addEventListener("click", () => this._moreInfo(e.highest));
    const panel = (id, open) => $(id)?.classList.toggle("open", open);
    $("reset")?.addEventListener("click", () => {
      panel("datepanel", false);
      panel("confirm", true);
    });
    $("confirm_no")?.addEventListener("click", () => panel("confirm", false));
    $("confirm_yes")?.addEventListener("click", () => {
      panel("confirm", false);
      this._call("button", "press", { entity_id: e.reset });
    });
    $("editdate")?.addEventListener("click", () => {
      panel("confirm", false);
      const input = $("dateinput");
      const today = localISO(new Date());
      input.max = today;
      const cur = this._hass.states[e.fdate]?.state;
      input.value = /^\d{4}-\d{2}-\d{2}$/.test(cur || "") ? cur : today;
      $("dateerr").textContent = "";
      panel("datepanel", true);
      input.focus();
    });
    $("dateinput")?.addEventListener("input", () => ($("dateerr").textContent = ""));
    $("date_no")?.addEventListener("click", () => panel("datepanel", false));
    $("date_yes")?.addEventListener("click", async () => {
      const v = $("dateinput").value;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) {
        $("dateerr").textContent = "Pick a date first.";
        return;
      }
      if (v > localISO(new Date())) {
        $("dateerr").textContent = "The date can't be in the future.";
        return;
      }
      panel("datepanel", false);
      await this._call("date", "set_value", { entity_id: e.fdate, date: v });
    });
    const chart = $("chart");
    const move = (ev) => {
      const svg = chart.querySelector("svg");
      if (!svg || !this._geom) return;
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * this._geom.W;
      if (px < this._geom.L || px > this._geom.W - this._geom.R) return this._hideTip();
      this._hover = this._geom.t(px);
      this._showTip(px, r);
    };
    chart.addEventListener("pointermove", move);
    chart.addEventListener("pointerdown", move);
    chart.addEventListener("pointerleave", () => this._hideTip());
    this._built = true;
    this._renderChart();
  }

  _update() {
    const e = this._e, hass = this._hass;
    const $ = (id) => this.shadowRoot.getElementById(id);
    if (!$("pill")) return;

    const vent = this._on(e.vent);
    const modes = modesFrom(this._on(e.g), this._on(e.y), this._on(e.o), this._on(e.w2), vent);
    const main = modes.filter((m) => m !== "vent");
    const pill = $("pill");
    const label = main.length ? main.map((m) => MODE_LABEL[m]).join(" + ") : vent ? MODE_LABEL.vent : "Idle";
    const color = MODE_COLOR[main[0] || (vent ? "vent" : "")];
    pill.textContent = label;
    pill.style.background = color ? `${color}26` : "";
    pill.style.color = color ? "var(--primary-text-color)" : "";

    const speed = hass.states[e.speed]?.state;
    const speedTxt = { low: "Low", medium_low: "Med-low", medium: "Medium" }[speed] || "";
    const chips = [
      [e.g, "G", "Fan"],
      [e.y, "Y", "Compressor"],
      [e.o, "O", "Cool valve"],
      [e.w2, "W2", "Heat strips"],
      [e.vent, "Vent", speedTxt || "CO₂ fan"],
    ]
      .filter(([id]) => id)
      .map(([id, k, n]) => `<span class="chip ${this._on(id) ? "on" : ""}" title="${esc(id)}"><i></i><b>${k}</b> ${esc(n)}</span>`)
      .join("");
    if ($("calls").innerHTML !== chips) $("calls").innerHTML = chips;

    const u = this._tempUnit();
    const temp = this._currentTemp(), hum = this._currentHum(), co2 = this._num(e.highest);
    $("v_temp").innerHTML = temp == null ? "—" : `${temp.toFixed(1)}<small> ${esc(u)}</small>`;
    $("s_temp").textContent = this._setpointText();
    $("v_hum").innerHTML = hum == null ? "—" : `${Math.round(hum)}<small> %</small>`;
    const hvacAction = hass.states[e.climate]?.attributes?.hvac_action;
    $("s_hum").textContent = hvacAction ? `Nest: ${String(hvacAction).replace(/_/g, " ")}` : "";
    $("v_co2").innerHTML = co2 == null ? "—" : `${Math.round(co2)}<small> ppm</small>`;
    const src = hass.states[e.highest]?.attributes?.source;
    $("s_co2").textContent = src ? (hass.states[src]?.attributes?.friendly_name || src).replace(/\s*(carbon dioxide|co2)\s*$/i, "") : "";

    $("rangetxt").textContent = `Last ${RANGES.find(([h]) => h === this._hours)?.[1].replace("7 d", "7 days").replace(" h", " hours") || this._hours + " hours"}`;
    $("range").querySelectorAll("button").forEach((b) => b.classList.toggle("on", Number(b.dataset.h) === this._hours));

    if ($("v_filter")) {
      const f = this._num(e.filter), tot = this._num(e.total);
      $("v_filter").innerHTML = `${fmtHours(f)}<small> h</small>`;
      $("v_total").innerHTML = `${fmtHours(tot)}<small> h</small>`;
      const changed = hass.states[e.fdate]?.state;
      const reset = hass.states[e.filter]?.attributes?.last_reset_at;
      if (/^\d{4}-\d{2}-\d{2}$/.test(changed || "")) {
        const [yy, mm, dd] = changed.split("-").map(Number);
        const d = new Date(yy, mm - 1, dd);
        const days = Math.round((new Date().setHours(0, 0, 0, 0) - d.getTime()) / 86400000);
        const ago = days <= 0 ? "today" : days === 1 ? "1 day ago" : `${days} days ago`;
        $("s_filter").textContent = `Changed ${d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}, ${ago}`;
      } else if (reset) {
        $("s_filter").textContent = `Since ${new Date(reset).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
      } else {
        $("s_filter").textContent = "Change date not set";
      }
      $("rundot").classList.toggle("on", !!hass.states[e.total]?.attributes?.running);
    }

    // Keep the live end of the chart fresh once a minute.
    if (Date.now() - (this._chartAt || 0) > 60000) this._renderChart();
  }

  _renderChart() {
    const box = this.shadowRoot.getElementById("svg");
    if (!box) return;
    this._chartAt = Date.now();
    const h = this._history;
    if (!h) {
      box.innerHTML = `<div class="sub" style="padding:40px 0;text-align:center">Loading history…</div>`;
      return;
    }
    if (h.error) {
      box.innerHTML = `<div class="sub" style="padding:40px 0;text-align:center">${esc(h.error)}</div>`;
      return;
    }
    const e = this._e;
    const W = 640, L = 40, R = 10;
    const start = h.start, end = Math.max(h.end, Date.now());
    const x = (t) => L + ((t - start) / (end - start)) * (W - L - R);
    this._geom = { W, L, R, t: (px) => start + ((px - L) / (W - L - R)) * (end - start) };
    const segs = this._segments();
    this._segs = segs;

    const num = (id) => (h.data[id] || []).map((p) => ({ t: p.t, v: parseFloat(p.s) })).filter((p) => Number.isFinite(p.v));
    const fromClimate = (key) => (h.climate || []).map((p) => ({ t: p.t, v: parseFloat(p.a?.[key]) })).filter((p) => Number.isFinite(p.v));
    const temp = e.temp ? num(e.temp) : fromClimate("current_temperature");
    const hum = e.hum ? num(e.hum) : fromClimate("current_humidity");
    const co2 = num(e.highest);
    const setLo = fromClimate("target_temp_low"), setHi = fromClimate("target_temp_high"), setOne = fromClimate("temperature");
    const nowAdd = (arr, v) => (v != null ? [...arr, { t: end, v }] : arr);
    this._lines = {
      temp: nowAdd(temp, this._currentTemp()),
      hum: nowAdd(hum, this._currentHum()),
      co2: nowAdd(co2, this._num(e.highest)),
    };

    let svg = `<svg viewBox="0 0 ${W} 430" width="100%" role="img" aria-label="Thermostat activity over the last ${this._hours} hours, with temperature, humidity and CO2 below on the same time axis">`;

    // Activity lanes
    svg += `<text x="${L}" y="11">Activity</text>`;
    MODES.forEach((m, i) => {
      const y0 = 18 + i * 13;
      svg += `<text x="${L - 6}" y="${y0 + 9}" text-anchor="end">${MODE_LANE[m]}</text>`;
      svg += `<rect x="${L}" y="${y0 + 1}" width="${W - L - R}" height="10" rx="2" fill="var(--divider-color)" opacity=".45"/>`;
      for (const s of segs) if (s.m === m) svg += `<rect x="${x(s.a).toFixed(1)}" y="${y0 + 1}" width="${Math.max(1.5, x(s.b) - x(s.a)).toFixed(1)}" height="10" rx="2" fill="${MODE_COLOR[m]}"/>`;
    });

    const u = this._tempUnit();
    const on = this._num(e.on), off = this._num(e.off);
    const setRefs = [];
    const setSeries = [];
    if (setLo.length && setHi.length) setSeries.push([setLo, "#eb6834"], [setHi, "#2a78d6"]);
    else if (setOne.length) setSeries.push([setOne, "#888780"]);
    svg += this._panel(`Temperature (${u})`, this._lines.temp, 106, 72, "#eb6834", segs, x, start, end, setSeries, 1);
    svg += this._panel("Humidity (%)", this._lines.hum, 204, 60, "#2a78d6", segs, x, start, end, [], 0);
    if (on != null) setRefs.push([on, "#d03b3b", `On ${Math.round(on)}`]);
    if (off != null) setRefs.push([off, "#0ca30c", `Off ${Math.round(off)}`]);
    svg += this._panel("Highest CO₂ (ppm)", this._lines.co2, 290, 92, "#1baf7a", segs, x, start, end, [], 0, setRefs);

    // Time axis
    const span = end - start;
    const stepH = this._hours <= 6 ? 1 : this._hours <= 24 ? 4 : 24;
    const first = new Date(start);
    first.setMinutes(0, 0, 0);
    if (stepH === 24) first.setHours(0);
    for (let t = first.getTime() + stepH * 3600000; t < end - span * 0.04; t += stepH * 3600000) {
      const d = new Date(t);
      if (stepH === 4 && d.getHours() % 4) continue;
      const lbl = stepH === 24 ? d.toLocaleDateString([], { weekday: "short" }) : d.getHours() === 0 ? d.toLocaleDateString([], { month: "short", day: "numeric" }) : d.toLocaleTimeString([], { hour: "numeric" });
      svg += `<text x="${x(t).toFixed(1)}" y="410" text-anchor="middle">${esc(lbl)}</text>`;
    }
    svg += `<text x="${W - R}" y="410" text-anchor="end">Now</text>`;
    svg += `<line id="cross" x1="0" x2="0" y1="18" y2="384" stroke="var(--secondary-text-color)" stroke-width="1" stroke-dasharray="2 3" visibility="hidden"/>`;
    svg += `</svg>`;
    box.innerHTML = svg;

    // Runtime totals for the window
    const totals = {};
    for (const s of segs) totals[s.m] = (totals[s.m] || 0) + (s.b - s.a);
    const show = ["heat", "strips", "cool", "vent"];
    const tot = this.shadowRoot.getElementById("totals");
    if (tot) tot.innerHTML = show.map((m) => `<div><div class="n"><i style="background:${MODE_COLOR[m]}"></i>${MODE_LABEL[m]}</div><div class="v">${fmtDur(totals[m] || 0)}</div></div>`).join("");
  }

  _panel(title, pts, y0, ph, color, segs, x, start, end, setSeries, decimals, refs = []) {
    let s = `<text x="${this._geom.L}" y="${y0 - 5}">${title}</text>`;
    for (const sg of segs) if (sg.m !== "fan") s += `<rect x="${x(sg.a).toFixed(1)}" y="${y0}" width="${Math.max(1, x(sg.b) - x(sg.a)).toFixed(1)}" height="${ph}" fill="${MODE_COLOR[sg.m]}" opacity="${sg.m === "vent" ? 0.1 : 0.13}"/>`;
    const vals = [...pts.map((p) => p.v), ...setSeries.flatMap(([a]) => a.map((p) => p.v)), ...refs.map(([v]) => v)];
    if (!pts.length) {
      s += `<rect x="${this._geom.L}" y="${y0}" width="${640 - this._geom.L - this._geom.R}" height="${ph}" fill="none" stroke="var(--divider-color)"/>`;
      s += `<text x="${(640 + this._geom.L) / 2}" y="${y0 + ph / 2 + 4}" text-anchor="middle">No data</text>`;
      return s;
    }
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = Math.max((hi - lo) * 0.12, decimals ? 0.5 : 2);
    lo -= pad;
    hi += pad;
    if (!decimals) {
      // Round the axis to tidy numbers (e.g. 550 / 750 / 950 ppm).
      const base = hi - lo > 300 ? 50 : hi - lo > 60 ? 10 : 2;
      lo = Math.floor(lo / (2 * base)) * 2 * base;
      hi = Math.ceil(hi / (2 * base)) * 2 * base;
    }
    const y = (v) => y0 + (1 - (v - lo) / (hi - lo)) * ph;
    for (let i = 0; i <= 2; i++) {
      const v = lo + ((hi - lo) * i) / 2;
      s += `<line x1="${this._geom.L}" x2="${640 - this._geom.R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--divider-color)" stroke-width="1"/>`;
      s += `<text x="${this._geom.L - 6}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${decimals ? v.toFixed(1) : Math.round(v)}</text>`;
    }
    for (const [v, c, t] of refs) {
      s += `<line x1="${this._geom.L}" x2="${640 - this._geom.R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${c}" stroke-dasharray="4 4" stroke-width="1.2"/>`;
      s += `<text x="${this._geom.L + 4}" y="${(y(v) - 3).toFixed(1)}" style="fill:${c}">${t}</text>`;
    }
    const step = (arr) => {
      let d = "", prev = null;
      for (const p of arr) {
        if (p.t < start) { prev = p; continue; }
        if (!d) d = `M${x(start).toFixed(1)},${y((prev || p).v).toFixed(1)}`;
        d += `H${x(p.t).toFixed(1)}V${y(p.v).toFixed(1)}`;
        prev = p;
      }
      if (prev) d = (d || `M${x(start).toFixed(1)},${y(prev.v).toFixed(1)}`) + `H${x(end).toFixed(1)}`;
      return d;
    };
    for (const [arr, c] of setSeries) s += `<path d="${step(arr)}" fill="none" stroke="${c}" stroke-width="1.2" stroke-dasharray="4 4"/>`;
    const inRange = pts.filter((p) => p.t >= start);
    const before = pts.filter((p) => p.t < start).pop();
    const line = [...(before ? [{ t: start, v: before.v }] : []), ...inRange];
    if (line.length > 1) s += `<path d="${line.map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join("")}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    const last = line[line.length - 1];
    if (last) s += `<circle cx="${x(last.t).toFixed(1)}" cy="${y(last.v).toFixed(1)}" r="4" fill="${color}" stroke="var(--card-background-color)" stroke-width="2"/>`;
    return s;
  }

  _showTip(px, rect) {
    const t = this._hover;
    const tip = this.shadowRoot.getElementById("tip");
    const cross = this.shadowRoot.getElementById("cross");
    if (!tip || !cross || t == null) return;
    cross.setAttribute("x1", px);
    cross.setAttribute("x2", px);
    cross.setAttribute("visibility", "visible");
    const near = (arr) => {
      let best = null;
      for (const p of arr || []) if (p.t <= t) best = p;
      return best ?? arr?.[0];
    };
    const modes = (this._segs || []).filter((s) => s.a <= t && s.b > t).map((s) => MODE_LABEL[s.m]);
    const tv = near(this._lines.temp), hv = near(this._lines.hum), cv = near(this._lines.co2);
    const d = new Date(t);
    const when = this._hours > 24 ? d.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    tip.innerHTML = `<b>${esc(when)}</b><br>${esc(modes.join(" + ") || "Idle")}<br>${tv ? `${tv.v.toFixed(1)} ${esc(this._tempUnit())}` : "—"} · ${hv ? `${Math.round(hv.v)} %` : "—"}<br>CO₂ ${cv ? Math.round(cv.v) : "—"} ppm`;
    tip.style.display = "block";
    const scale = rect.width / this._geom.W;
    const left = px * scale;
    const w = tip.offsetWidth;
    tip.style.left = `${left + 10 + w > rect.width ? left - w - 10 : left + 10}px`;
    tip.style.top = `${106 * scale}px`;
  }

  _hideTip() {
    this._hover = null;
    const tip = this.shadowRoot.getElementById("tip");
    const cross = this.shadowRoot.getElementById("cross");
    if (tip) tip.style.display = "none";
    if (cross) cross.setAttribute("visibility", "hidden");
  }
}

if (!customElements.get("co2-thermostat-card")) {
  customElements.define("co2-thermostat-card", Co2ThermostatCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "co2-thermostat-card",
    name: "CO2 Ventilation: thermostat history",
    description: "What the thermostat is calling for, 24-hour activity with temperature, humidity and CO2, and fan runtime with a filter reset.",
    preview: false,
    documentationURL: "https://github.com/stephencorrell-ops/ha-co2-ventilation",
  });
}
})();
