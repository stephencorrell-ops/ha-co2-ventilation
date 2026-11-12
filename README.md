# CO2 Ventilation for Home Assistant

Runs your HVAC fan (or any switch, fan, or input boolean) when indoor CO2 gets high, and turns it back off once the air is fresh, with sliders for everything.

- **Fan on at / Fan off at** setpoints with hysteresis (defaults 900 / 700 ppm)
- **Minimum run time**, so the fan doesn't short-cycle (default 20 min)
- **Auto ventilation** switch to turn the routine on or off without touching the fan
- **Ventilation speed** (Low, Medium-low, Medium, Medium-high; default Low) for multi-speed fans, so CO2 ventilation can run quietly instead of at full speed
- **Safe restarts**: after Home Assistant starts, it waits for your sensors to report (default 2 min), then turns the fan off unless CO2 is already above the on setpoint
- **Highest CO2** and **Status** sensors for your dashboard
- **Fan runtime**: hours since the last filter change (with a reset button) and a lifetime total
- **Thermostat history card** showing what the thermostat is doing, with temperature, humidity and CO2

## Install with HACS

1. In HACS, open the menu (three dots) and pick **Custom repositories**.
2. Add `https://github.com/stephencorrell-ops/ha-co2-ventilation` with type **Integration**.
3. Search HACS for **CO2 Ventilation**, download it, and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration → CO2 Ventilation**.
5. Pick the CO2 sensors that should drive the fan, and the fan to control.

To change sensors, the fan, or the startup delay later, use **Configure** on the integration.

> Turn off any old automation that controls the same fan, or the two will fight.

## How it decides

| CO2 (highest of your sensors) | What happens |
| --- | --- |
| At or above **Fan on at** | Fan turns on |
| Between the setpoints | Fan keeps doing what it's doing |
| Below **Fan off at** on every sensor | Fan turns off once it has run for the **Minimum run time** |

- Sensors that are `unavailable` or `unknown` are skipped, which helps with Bluetooth sensors that miss a reading now and then.
- If you turn the fan on by hand, it stays on until you turn it off. If CO2 crosses the on setpoint while it's running, auto ventilation takes over and will shut it off when the air is clear.
- **Remote fan** (`select.co2_ventilation_remote_fan`, also a row of buttons on the CO2 card): Off, Low, Medium-low, Medium or Medium-high, for button or remote automations. A speed runs the fan at that speed (higher if CO2 or the shower need more, and it works with Auto ventilation off); Off turns it off unless CO2 or the shower still need it. Turning the fan off any other way sets it back to Off, and it's Off after a restart. Runs started this way show as Remote on the cards.
- Turning **Auto ventilation** off leaves the fan exactly as it is.

## Ventilation speed

If the fan you pick is a multi-speed `fan` entity (for example an ESPHome fan with `speed_count: 4`), auto ventilation turns it on at the **Ventilation speed**: Low (speed 1) by default, or Medium-low (2), Medium (3) or Medium-high (4). On a fan with fewer speeds, a higher choice runs at its top speed. Changing the speed while auto ventilation is running the fan applies right away. A fan you turned on by hand keeps the speed you gave it. With a switch or input boolean, the speed setting has no effect and the fan simply turns on.

## Entities

With the default name, the entity IDs are:

| Entity | What it is |
| --- | --- |
| `switch.co2_ventilation_auto_ventilation` | Routine on/off |
| `number.co2_ventilation_fan_on_at` | On setpoint (ppm) |
| `number.co2_ventilation_fan_off_at` | Off setpoint (ppm) |
| `number.co2_ventilation_minimum_run_time` | Minimum run (minutes) |
| `select.co2_ventilation_ventilation_speed` | Low, Medium-low, Medium, or Medium-high; the speed auto ventilation uses |
| `sensor.co2_ventilation_highest_co2` | Reading being acted on; `source` attribute names the room |
| `sensor.co2_ventilation_fan_runtime_since_filter_change` | Blower hours since the filter was last reset |
| `sensor.co2_ventilation_fan_runtime_total` | Lifetime blower hours (never resets) |
| `button.co2_ventilation_reset_filter_runtime` | Press after changing the filter; also sets the date below to today |
| `date.co2_ventilation_last_filter_change` | When the filter was last changed; set it by hand for an earlier change |
| `sensor.co2_ventilation_hvac_activity` | What the HVAC is doing: Idle, Heat pump heating, Heat pump + heat strips, Heat strips, Cooling, Defrost, Fan only, CO2 ventilating, Fan on by hand, Fan on by remote. Attributes say who called for it (`called_by`: thermostat, co2, humidity, remote, manual), the thermostat's name, and the speed the blower is actually running (`fan_speed`) |
| `sensor.co2_ventilation_fan_turned_on_by` | Who has the fan on: Off, CO2, Shower humidity, Remote (the Remote fan select), By hand. Its history splits CO2 runs from remote ones on the thermostat card |
| `sensor.co2_ventilation_status` | Idle, Ventilating, Finishing minimum run, Fan on manually, Auto off, Starting up, No sensor data |

## Shower humidity

Under **Configure → Shower humidity (optional)**, pick:

- **Bathroom humidity sensor**
- **House humidity sensor**: leave empty to use the thermostat's humidity sensor
- **Bathroom exhaust fan** (optional): a switch, fan, light or input boolean. It runs for the shower only if the air conditioning ran within the **Exhaust fan cooling window** (7 days by default), detected as 10 minutes of the Y and O calls without the heat strips (a defrost cycle has W2 on too, so it never counts), or the thermostat reporting cooling for 10 minutes. In heating season it stays off so the shower's moisture helps humidify the house; the HVAC blower still spreads it around. Once started, it runs to the end of that shower.

How it runs, in humidity points of the bathroom above the house (52 % against 40 % is +12):

1. Above **On above** (+10): the fan runs at its top speed.
2. Below **High until** (+20), after at least 5 minutes on high: it drops to low.
3. Below **Off below** (+5): off.

**Shower maximum run** (90 minutes) stops it if the bathroom never dries out, and it then waits for the bathroom to come back near the house before it can start again. If the bathroom sensor goes unavailable it stops. Turning the fan off by hand during a shower keeps it off until that shower is over. **Shower ventilation** turns the whole feature on or off.

The shower and CO2 share the fan: it runs at the higher of the two speeds and only turns off when neither needs it.

| Entity | What it is |
|---|---|
| `switch.co2_ventilation_shower_ventilation` | Turns shower ventilation on or off |
| `sensor.co2_ventilation_bathroom_humidity_above_house` | Bathroom minus house, with the current mode (off, high, low, lockout) |
| `number.co2_ventilation_shower_on_above_house` | On above (default +10) |
| `number.co2_ventilation_shower_high_until` | High until (default +20) |
| `number.co2_ventilation_shower_off_below` | Off below (default +5) |
| `number.co2_ventilation_shower_maximum_run` | Maximum run (default 90 minutes) |
| `number.co2_ventilation_exhaust_fan_cooling_window` | Exhaust fan runs only if cooling ran within this many days (default 7; only with an exhaust fan) |
| `sensor.co2_ventilation_last_cooling_run` | When the air conditioning last ran (only with an exhaust fan) |

## Thermostat and fan runtime

Under **Configure**, the optional **Thermostat** section takes:

- **Thermostat**: your climate entity (for example the Nest), used for the setpoint and as a fallback for temperature and humidity
- **Temperature sensor** and **Humidity sensor**: for example the Nest's own sensors
- **Fan call (G)**, **Compressor call (Y)**, **Reversing valve (O, on in cooling)**, **Heat strips (W2/AUX)**: binary sensors for the 24 V thermostat signals, for example from an ESPHome board at the air handler

The blower counts as running whenever the fan call, the heat strip call, or the ventilation fan is on. Without the call inputs, only the ventilation fan is counted.

### Thermostat history card

Add **CO2 Ventilation: thermostat history** from **Add card**, or use `type: custom:co2-thermostat-card`. It shows the current calls, temperature, humidity and highest CO2, a timeline of heat pump, heat strip, cooling, fan only and ventilation runs, three charts on the same time axis with those runs shaded behind them, run totals for the window, and the fan runtime counters with a two-tap filter reset.

```yaml
type: custom:co2-thermostat-card
hours: 24          # 6, 24 or 168; the card has buttons for these too
title: Thermostat  # optional
```

## Dashboard card

The integration ships its own card; there's nothing extra to install. After a restart (and a browser refresh), edit a dashboard, choose **Add card**, and pick **CO2 Ventilation**. It finds your sensors and fan automatically and shows:

- Each room's CO2, colored green / amber / red against your setpoints (tap a room for its history)
- Auto ventilation and HVAC fan toggles, with minutes left on the minimum run
- Low / Med-low / Medium speed buttons when the fan has speeds (turning the fan on from the card uses the selected speed)
- Setpoint and minimum run controls, locked by default so a stray touch can't change them. Tap **Unlock**, then drag a slider or tap the number and type a value. They lock again 10 seconds after a change (30 seconds if you don't touch anything).
- A chart of the last 6 hours, 24 hours or 7 days (buttons on the card) with fan run time shaded and live setpoint lines

Options, all optional:

```yaml
type: custom:co2-ventilation-card
title: CO₂ ventilation
hours: 24                 # starting chart span: 6, 24 or 168; the card has buttons for these too
show_chart: true
extra_sensors:            # rooms to show but not control the fan
  - sensor.basement_co2_carbon_dioxide
# entity: sensor.co2_ventilation_status   # only needed with more than one setup
```

The integration adds the card to your dashboard resources automatically (and keeps its version current on updates). If you see "Custom element doesn't exist", refresh the browser or the app (Settings → Companion app → Debugging → Reset frontend cache). If your dashboards' resources are managed in YAML, add `/co2_ventilation/co2-ventilation-card.js` as a JavaScript module yourself.

## Build your own dashboard

If you'd rather assemble cards yourself, here's the YAML.

### Controls

```yaml
type: entities
title: CO₂ ventilation
entities:
  - entity: sensor.co2_ventilation_status
  - entity: switch.co2_ventilation_auto_ventilation
  - entity: switch.house_fan_control
    name: HVAC fan
  - entity: number.co2_ventilation_fan_on_at
  - entity: number.co2_ventilation_fan_off_at
  - entity: number.co2_ventilation_minimum_run_time
  - entity: select.co2_ventilation_ventilation_speed
```

### Chart with live setpoint lines

Needs [apexcharts-card](https://github.com/RomRider/apexcharts-card) from HACS. Swap in your own sensors and fan.

```yaml
type: custom:apexcharts-card
graph_span: 24h
header:
  show: true
  title: CO₂ vs fan
  show_states: true
  colorize_states: true
apex_config:
  chart:
    height: 320
  legend:
    show: false
yaxis:
  - id: co2
    min: 400
    max: 1200
    decimals: 0
  - id: fan
    show: false
    min: 0
    max: 1
series:
  - entity: switch.house_fan_control
    name: Fan
    yaxis_id: fan
    type: area
    curve: stepline
    color: '#f1c40f'
    opacity: 0.2
    stroke_width: 0
    transform: "return x === 'on' ? 1 : 0;"
    show: {in_header: false}
  - entity: number.co2_ventilation_fan_on_at
    name: On setpoint
    yaxis_id: co2
    curve: stepline
    color: '#d03b3b'
    stroke_width: 1.5
    stroke_dash: 4
    show: {in_header: false}
  - entity: number.co2_ventilation_fan_off_at
    name: Off setpoint
    yaxis_id: co2
    curve: stepline
    color: '#0ca30c'
    stroke_width: 1.5
    stroke_dash: 4
    show: {in_header: false}
  - entity: sensor.meter_pro_co2_a0cf_carbon_dioxide
    name: Bedroom
    yaxis_id: co2
    color: '#2a78d6'
    group_by: {func: avg, duration: 5min}
  - entity: sensor.living_room_co2_carbon_dioxide
    name: Living
    yaxis_id: co2
    color: '#1baf7a'
    group_by: {func: avg, duration: 5min}
  - entity: sensor.claires_room_co2_carbon_dioxide
    name: Claire
    yaxis_id: co2
    color: '#eda100'
    group_by: {func: avg, duration: 5min}
  - entity: sensor.corbins_room_co2_carbon_dioxide
    name: Corbin
    yaxis_id: co2
    color: '#eb6834'
    group_by: {func: avg, duration: 5min}
  - entity: sensor.basement_co2_carbon_dioxide
    name: Basement
    yaxis_id: co2
    color: '#6250d6'
    group_by: {func: avg, duration: 5min}
```

### Room gauges

```yaml
type: gauge
entity: sensor.meter_pro_co2_a0cf_carbon_dioxide
name: Bedroom
min: 400
max: 1500
needle: true
severity: {green: 400, yellow: 800, red: 900}
```

Repeat for each room inside a `grid` card with `columns: 3`.
