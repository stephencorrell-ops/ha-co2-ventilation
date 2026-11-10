"""Setpoint and minimum run time sliders."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION, PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import Co2VentilationConfigEntry
from .const import (
    DEFAULT_MIN_RUN,
    DEFAULT_OFF_SETPOINT,
    DEFAULT_ON_SETPOINT,
    DOMAIN,
    MIN_RUN_MAX,
    SETPOINT_MAX,
    SETPOINT_MIN,
    SETPOINT_STEP,
)
from .controller import Co2VentilationController
from .entity import Co2VentilationEntity
from .humidity import (
    DEFAULT_HIGH_UNTIL,
    DEFAULT_MAX_RUN,
    DEFAULT_OFF_DELTA,
    DEFAULT_ON_DELTA,
    DELTA_MAX,
    MAX_RUN_MAX,
)


@dataclass(frozen=True, kw_only=True)
class _Spec:
    key: str
    default: float
    min_value: float
    max_value: float
    step: float
    unit: str
    device_class: NumberDeviceClass | None
    icon: str


SPECS = (
    _Spec(
        key="on_setpoint",
        default=DEFAULT_ON_SETPOINT,
        min_value=SETPOINT_MIN,
        max_value=SETPOINT_MAX,
        step=SETPOINT_STEP,
        unit=CONCENTRATION_PARTS_PER_MILLION,
        device_class=NumberDeviceClass.CO2,
        icon="mdi:arrow-collapse-up",
    ),
    _Spec(
        key="off_setpoint",
        default=DEFAULT_OFF_SETPOINT,
        min_value=SETPOINT_MIN,
        max_value=SETPOINT_MAX,
        step=SETPOINT_STEP,
        unit=CONCENTRATION_PARTS_PER_MILLION,
        device_class=NumberDeviceClass.CO2,
        icon="mdi:arrow-collapse-down",
    ),
    _Spec(
        key="min_run",
        default=DEFAULT_MIN_RUN,
        min_value=0,
        max_value=MIN_RUN_MAX,
        step=5,
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
        icon="mdi:timer-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    entities: list[Co2VentilationEntity] = [
        Co2SetpointNumber(controller, spec) for spec in SPECS
    ]
    if controller.shower_configured:
        entities += [ShowerNumber(controller, spec) for spec in SHOWER_SPECS]
    async_add_entities(entities)


class Co2SetpointNumber(Co2VentilationEntity, RestoreNumber):
    """A slider that feeds a value into the controller."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller: Co2VentilationController, spec: _Spec) -> None:
        super().__init__(controller, spec.key)
        self._spec = spec
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_icon = spec.icon
        self._attr_native_value = spec.default

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
        self._push(self._attr_native_value)

    def _push(self, value: float) -> None:
        key = self._spec.key
        if key == "on_setpoint":
            self.controller.on_setpoint = value
        elif key == "off_setpoint":
            self.controller.off_setpoint = value
        else:
            self.controller.min_run_minutes = value

    @property
    def native_value(self) -> float:
        key = self._spec.key
        if key == "on_setpoint":
            return self.controller.on_setpoint
        if key == "off_setpoint":
            return self.controller.off_setpoint
        return self.controller.min_run_minutes

    async def async_set_native_value(self, value: float) -> None:
        key = self._spec.key
        if key == "on_setpoint" and value <= self.controller.off_setpoint:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="on_below_off",
                translation_placeholders={"off": str(int(self.controller.off_setpoint))},
            )
        if key == "off_setpoint" and value >= self.controller.on_setpoint:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="off_above_on",
                translation_placeholders={"on": str(int(self.controller.on_setpoint))},
            )
        self._attr_native_value = value
        if key == "on_setpoint":
            self.controller.set_setpoints(on_setpoint=value)
        elif key == "off_setpoint":
            self.controller.set_setpoints(off_setpoint=value)
        else:
            self.controller.set_setpoints(min_run_minutes=value)



# Shower humidity thresholds, in humidity points above the house.
SHOWER_SPECS = (
    _Spec(
        key="on_delta",
        default=DEFAULT_ON_DELTA,
        min_value=1,
        max_value=DELTA_MAX,
        step=1,
        unit=PERCENTAGE,
        device_class=None,
        icon="mdi:water-plus",
    ),
    _Spec(
        key="high_until",
        default=DEFAULT_HIGH_UNTIL,
        min_value=1,
        max_value=DELTA_MAX,
        step=1,
        unit=PERCENTAGE,
        device_class=None,
        icon="mdi:fan-chevron-down",
    ),
    _Spec(
        key="off_delta",
        default=DEFAULT_OFF_DELTA,
        min_value=0,
        max_value=DELTA_MAX,
        step=1,
        unit=PERCENTAGE,
        device_class=None,
        icon="mdi:water-minus",
    ),
    _Spec(
        key="max_run_minutes",
        default=DEFAULT_MAX_RUN,
        min_value=10,
        max_value=MAX_RUN_MAX,
        step=5,
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
        icon="mdi:timer-stop-outline",
    ),
)


class ShowerNumber(Co2VentilationEntity, RestoreNumber):
    """A shower humidity threshold or the maximum run time."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, controller: Co2VentilationController, spec: _Spec) -> None:
        super().__init__(controller, f"shower_{spec.key}")
        self._spec = spec
        self._attr_native_min_value = spec.min_value
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_class = spec.device_class
        self._attr_icon = spec.icon

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            setattr(self.controller.shower.settings, self._spec.key, last.native_value)

    @property
    def native_value(self) -> float:
        return getattr(self.controller.shower.settings, self._spec.key)

    async def async_set_native_value(self, value: float) -> None:
        s = self.controller.shower.settings
        key = self._spec.key
        off = value if key == "off_delta" else s.off_delta
        on = value if key == "on_delta" else s.on_delta
        high = value if key == "high_until" else s.high_until
        if key != "max_run_minutes" and (off >= on or off >= high):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="shower_off_too_high",
            )
        self.controller.set_shower_settings(**{key: value})
