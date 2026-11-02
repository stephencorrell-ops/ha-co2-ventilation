# Changelog

All notable changes to CO2 Ventilation. Newest first.

After updating in HACS, restart Home Assistant and refresh your dashboard (close and reopen the app on a phone or tablet) so the new card loads.

## 0.3.3

- Fixed the card failing to load next to other custom cards, and wrapped it so its names stay private.
- Restored the integration's manifest file, which an earlier 0.3.3 commit emptied by mistake and which made HACS fail with an empty-document error.

## 0.3.2

- The card's address changes whenever the file changes, so the Home Assistant app fetches new versions instead of using its saved copy.
