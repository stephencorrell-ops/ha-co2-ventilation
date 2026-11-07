# Changelog

All notable changes to CO2 Ventilation. Newest first.

After updating in HACS, restart Home Assistant and refresh your dashboard (close and reopen the app on a phone or tablet) so the new card loads.

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
