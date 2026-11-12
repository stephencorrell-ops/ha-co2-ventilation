# Changelog

All notable changes to CO2 Ventilation. Newest first.

After updating in HACS, restart Home Assistant and refresh your dashboard (close and reopen the app on a phone or tablet) so the new card loads.

## 0.16.1

- CO2 card: a **Remote fan** row under CO2 speed with Off, Low, Med-low, Medium and Med-high buttons, so you can run the fan at a speed from the card. It's the same Remote fan select your automations can set.

## 0.16.0

- New **Remote fan** select for button and remote automations: Off, Low, Medium-low, Medium or Medium-high. Pick a speed and the fan runs at it (or higher if CO2 or the shower need more, and it works with Auto ventilation off); pick Off and it turns off unless CO2 or the shower still need it. Turning the fan off any other way sets it back to Off, and it starts Off after a restart. These runs show as **Remote** on both cards, the HVAC activity sensor and the Fan turned on by sensor.
- Removed the 0.15.0 **Fan remotes** setting (the 30 second press window). Point your remote automations at the Remote fan select instead. A fan turned on any other way shows as By hand.

## 0.15.0

- New optional setting **Fan remotes** under Configure: pick the buttons or remotes whose automations run the fan. When the fan comes on within 30 seconds of a press, it's shown as turned on **by remote** instead of by hand: the CO2 card's status row reads "Turned on by remote", and the HVAC activity sensor shows **Fan on by remote** (`called_by: remote`).
- New **Fan turned on by** sensor: Off, CO2, Shower humidity, Remote or By hand.
- Thermostat card: a new **Remote** lane in the chart for fan runs started by a remote or by hand, so they no longer show as CO2 ventilation. The status pill, Vent chip and tooltip say Remote or By hand, and the totals row adds Remote / by hand when it ran. Earlier runs that were by hand land in the Remote lane too.
- Thermostat card: the 24 hour chart shows its time labels again (12 AM, 4 AM, 8 AM...). They were skipped unless the chart happened to start on one of those hours. Each label also gets a small tick mark.

## 0.14.0

- New setting under Thermostat: **Name for a fan-only call (G)**. If something besides the thermostat calls G (a humidifier, for example), name it here, like `Fan/Humidifier`. Both cards use it for the status, the G chip, the legend and the chart tooltip, and the HVAC activity sensor shows it as `g_label`. Leave it blank to keep "Fan only".

## 0.13.0

- Shower humidity: the house reference can be several humidity sensors, averaged (offline ones are skipped). Leave it empty to keep using the thermostat's humidity. Existing single-sensor setups carry over.
- CO2 card: a small bar under the Shower row while it's clearing humidity, with tick marks at the off, on and high-until settings, a marker at the shower's peak, and an estimate of how long until the fan turns off. Hidden between showers.

## 0.12.0

- New **shower humidity ventilation**. Pick a bathroom humidity sensor under Configure → Shower humidity. When the bathroom gets well above the house's humidity, the fan runs at its top speed; once it falls back it drops to low; when it's close to the house again it turns off. Defaults: on at +10, high until +20, off below +5 (humidity points), with high held at least 5 minutes and a 90 minute maximum run. A dead sensor stops it, and a fan switched off by hand mid-shower stays off for that shower.
- The house reference is the thermostat's humidity sensor unless you pick another one.
- Shower and CO2 share the fan: it runs at whichever speed is higher and only turns off when neither needs it.
- Optional bathroom exhaust fan for the shower, but only in cooling season: it runs only if the air conditioning ran in the last 7 days (adjustable). Cooling counts only after 10 minutes of Y and O without the heat strips, so a defrost cycle (Y, O and W2 together) never looks like cooling; without the call inputs it uses the thermostat reporting cooling for 10 minutes. In heating season the shower's moisture stays in the house to help the humidifier, while the HVAC blower still spreads it around. A new Last cooling run sensor remembers when cooling last ran, across restarts.
- The HVAC activity sensor and both cards now show a defrost cycle (Y, O and W2 together) as **Defrost** instead of cooling plus heat strips.
- The CO2 card shows a Shower row with the bathroom's humidity over the house, and the shower thresholds next to the CO2 setpoints. The status row shows shower humidity as a caller. The speed buttons are now labelled CO2 speed.

## 0.11.0

- New **HVAC activity** sensor: what the system is running (heat pump, heat strips, cooling, fan only, CO2 ventilation, fan on by hand, or idle), who called for it (your thermostat, CO2, or by hand), and the speed the blower is actually at. The highest energized speed wins, so a Nest call at Medium and ventilation at Low shows Medium.
- The **CO2 ventilation card** has a new status row under the title, for example "Heat pump heating, called by Nest" or "Ventilating, called by CO2, Front room 912 ppm". Its fan spins whenever the blower runs, faster at higher speeds, and the row shows the actual fan speed. This replaces the fan and speed pill that were in the header. The header pill still shows the CO2 routine, now reading **CO2 OK** instead of Idle.
- New **Medium-high** ventilation speed for 4-speed fans.
- The thermostat card's fan spins at the blower's actual speed.

## 0.10.0

- On the **CO2 ventilation card**, the spinning fan moved to the top right next to the status, matching the thermostat card. Beside it, a **speed pill** shows the speed the fan is actually running at (Low, Med-low, Medium). It hides when the fan is off or has no speeds.
- Chart time labels that would be cut off at the left or right edge are no longer drawn.

## 0.9.0

- Both cards now show a **spinning fan** while the blower runs. On the CO2 card it's the HVAC fan icon, and it spins faster at Med-low and Medium. On the thermostat card it sits next to the status pill and spins for any thermostat call (fastest during heating or cooling) or for ventilation. It stays still if your device is set to reduce motion.

## 0.8.0

- The **CO2 ventilation card** now has the same **6 h / 24 h / 7 d** buttons as the thermostat card to change the chart's time span. The card's `hours:` setting still picks which one it opens on.

## 0.7.0

- New **Last filter change** date. Pressing reset sets it to today; you can also type in an earlier date (for a change made before the counters existed) without touching the runtime hours. Future dates are refused.
- The card shows the date and how many days ago it was, with **Change date** to edit it.
- **Reset filter** on the card now asks before resetting, with Cancel and Reset buttons, instead of a tap-twice button.

## 0.6.0

- New **thermostat history card** (CO2 Ventilation: thermostat history). It shows what the thermostat is calling for right now (G, Y, O, W2 and the ventilation fan), current temperature, humidity and CO2, and a 6 hour, 24 hour or 7 day timeline of heat pump, heat strip, cooling, fan and ventilation runs with temperature, humidity and CO2 charts underneath. Hover or tap the chart for the readings at any moment.
- **Fan runtime counters**: hours the blower has run since the last filter change, and a lifetime total that never resets. Press **Reset filter runtime** (or the button on the card) after a filter change.
- New optional **Thermostat** section under Configure: pick your thermostat, temperature and humidity sensors, and the four 24 V call inputs. Everything here is optional, and without it the runtime counters count the ventilation fan only.

## 0.5.0

- New **Ventilation speed** setting (Low, Medium-low, Medium). With a multi-speed fan, auto ventilation now runs it at the selected speed, Low by default, instead of whatever speed the fan last used. Changing the speed while it's ventilating applies right away; a fan turned on by hand is left at its own speed.
- The card shows Low / Med-low / Medium buttons when the fan has speeds, and its fan toggle turns the fan on at the selected speed.
- Switches and input booleans work as before.

## 0.4.0

- Setpoint sliders in the card start locked and ignore touches until Unlock is tapped, then relock automatically. Each value can also be typed in.

## 0.3.4

- The dashboard resource address no longer carries a changing ?v= number. With it, the card failed to load in the Home Assistant app and in Safari. The integration also puts an older ?v= address back to the plain one.

## 0.3.3

- Fixed the card failing to load next to other custom cards, and wrapped it so its names stay private.
- Restored the integration's manifest file, which an earlier 0.3.3 commit emptied by mistake and which made HACS fail with an empty-document error.

## 0.3.2

- The card's address changes whenever the file changes, so the Home Assistant app fetches new versions instead of using its saved copy.
