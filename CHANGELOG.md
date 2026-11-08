# Changelog

All notable changes to CO2 Ventilation. Newest first.

After updating in HACS, restart Home Assistant and refresh your dashboard (close and reopen the app on a phone or tablet) so the new card loads.

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
