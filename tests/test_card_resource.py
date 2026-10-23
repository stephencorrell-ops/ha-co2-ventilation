"""Dashboard resource registration."""

from types import SimpleNamespace

from homeassistant.core import HomeAssistant

from custom_components.co2_ventilation import CARD_URL, _async_ensure_lovelace_resource


class FakeResources:
    def __init__(self, items=None):
        self.items = list(items or [])
        self.loaded = True

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, data):
        self.items.append({"id": str(len(self.items) + 1), **data})

    async def async_update_item(self, item_id, data):
        for item in self.items:
            if item["id"] == item_id:
                item.update(data)


async def test_adds_resource(hass: HomeAssistant) -> None:
    res = FakeResources()
    hass.data["lovelace"] = SimpleNamespace(resources=res)
    await _async_ensure_lovelace_resource(hass, f"{CARD_URL}?v=1")
    assert res.items == [{"id": "1", "res_type": "module", "url": f"{CARD_URL}?v=1"}]


async def test_updates_existing_without_duplicate(hass: HomeAssistant) -> None:
    res = FakeResources([{"id": "7", "res_type": "module", "url": f"{CARD_URL}?v=0.2.3"}])
    hass.data["lovelace"] = SimpleNamespace(resources=res)
    await _async_ensure_lovelace_resource(hass, f"{CARD_URL}?v=0.3.0")
    assert len(res.items) == 1
    assert res.items[0]["url"] == f"{CARD_URL}?v=0.3.0"
    await _async_ensure_lovelace_resource(hass, f"{CARD_URL}?v=0.3.0")
    assert len(res.items) == 1


async def test_leaves_other_resources(hass: HomeAssistant) -> None:
    res = FakeResources([{"id": "1", "res_type": "module", "url": "/hacsfiles/apexcharts-card.js"}])
    hass.data["lovelace"] = SimpleNamespace(resources=res)
    await _async_ensure_lovelace_resource(hass, f"{CARD_URL}?v=1")
    assert [i["url"] for i in res.items] == ["/hacsfiles/apexcharts-card.js", f"{CARD_URL}?v=1"]


async def test_yaml_mode_is_skipped(hass: HomeAssistant) -> None:
    hass.data["lovelace"] = SimpleNamespace(resources=SimpleNamespace())
    await _async_ensure_lovelace_resource(hass, f"{CARD_URL}?v=1")
