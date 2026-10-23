# CO2 Ventilation for Home Assistant

Runs your HVAC fan (or any switch, fan, or input boolean) when indoor CO2 gets high, and turns it back off once the air is fresh, with sliders for everything.

- **Fan on at / Fan off at** setpoints with hysteresis (defaults 900 / 700 ppm)
- **Minimum run time**, so the fan doesn't short-cycle (default 20 min)
- **Auto ventilation** switch to turn the routine on or off without touching the fan
- **Safe restarts**: after Home Assistant starts, it waits for your sensors to report (default 2 min), then turns the fan off unless CO2 is already above the on setpoint
- **Highest CO2** and **Status** sensors for your dashboard

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
- Turning **Auto ventilation** off leaves the fan exactly as it is.

## Entities

With the default name, the entity IDs are:

| Entity | What it is |
| --- | --- |
| `switch.co2_ventilation_auto_ventilation` | Routine on/off |
| `number.co2_ventilation_fan_on_at` | On setpoint (ppm) |
| `number.co2_ventilation_fan_off_at` | Off setpoint (ppm) |
| `number.co2_ventilation_minimum_run_time` | Minimum run (minutes) |
| `sensor.co2_ventilation_highest_co2` | Reading being acted on; `source` attribute names the room |
| `sensor.co2_ventilation_status` | Idle, Ventilating, Finishing minimum run, Fan on manually, Auto off, Starting up, No sensor data |

## Dashboard

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
