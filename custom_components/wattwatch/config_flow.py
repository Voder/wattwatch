"""Config flow for WattWatch integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CONSECUTIVE_REQUIRED,
    CONF_COOLDOWN,
    CONF_ENTITIES,
    CONF_MIN_DEVIATION,
    CONF_MIN_SAMPLES,
    CONF_MONITOR_DIRECTIONS,
    CONF_THRESHOLD,
    CONF_WINDOW_SIZE,
    DEFAULT_CONSECUTIVE_REQUIRED,
    DEFAULT_COOLDOWN,
    DEFAULT_DIRECTION,
    DEFAULT_MIN_DEVIATION,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    DIRECTION_BOTH,
    DIRECTION_HIGH,
    DIRECTION_LOW,
    DOMAIN,
)

ENTITY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITIES): EntitySelector(
            EntitySelectorConfig(
                domain="sensor",
                device_class="power",
                multiple=True,
            )
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_WINDOW_SIZE, default=DEFAULT_WINDOW_SIZE
        ): NumberSelector(
            NumberSelectorConfig(
                min=10, max=1000, step=1, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_THRESHOLD, default=DEFAULT_THRESHOLD
        ): NumberSelector(
            NumberSelectorConfig(
                min=1.0, max=10.0, step=0.1, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_COOLDOWN, default=DEFAULT_COOLDOWN
        ): NumberSelector(
            NumberSelectorConfig(
                min=0, max=3600, step=1, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_MIN_SAMPLES, default=DEFAULT_MIN_SAMPLES
        ): NumberSelector(
            NumberSelectorConfig(
                min=3, max=50, step=1, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_MIN_DEVIATION, default=DEFAULT_MIN_DEVIATION
        ): NumberSelector(
            NumberSelectorConfig(
                min=0.0, max=1000.0, step=0.1, mode=NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_CONSECUTIVE_REQUIRED, default=DEFAULT_CONSECUTIVE_REQUIRED
        ): NumberSelector(
            NumberSelectorConfig(
                min=1, max=20, step=1, mode=NumberSelectorMode.BOX
            )
        ),
    }
)

DIRECTION_OPTIONS = [
    {"value": DIRECTION_BOTH, "label": "Both (high and low)"},
    {"value": DIRECTION_HIGH, "label": "High only (spikes)"},
    {"value": DIRECTION_LOW, "label": "Low only (drops)"},
]


def _build_directions_schema(
    entities: list[str],
    current_directions: dict[str, str] | None = None,
) -> vol.Schema:
    """Build a schema with a direction selector per entity."""
    if current_directions is None:
        current_directions = {}

    fields: dict[Any, Any] = {}
    for entity_id in entities:
        entity_name = entity_id.split(".")[-1]
        default = current_directions.get(entity_id, DEFAULT_DIRECTION)
        fields[vol.Required(entity_id, default=default)] = SelectSelector(
            SelectSelectorConfig(
                options=DIRECTION_OPTIONS,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=entity_name,
            )
        )

    return vol.Schema(fields)


class WattWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WattWatch."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._entities: list[str] = []
        self._options_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle entity selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_ENTITIES):
                errors["base"] = "no_entities"
            else:
                self._entities = user_input[CONF_ENTITIES]
                return await self.async_step_options()

        return self.async_show_form(
            step_id="user",
            data_schema=ENTITY_SCHEMA,
            errors=errors,
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle detection settings step."""
        if user_input is not None:
            self._options_input = user_input
            return await self.async_step_directions()

        return self.async_show_form(
            step_id="options",
            data_schema=OPTIONS_SCHEMA,
        )

    async def async_step_directions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle per-entity direction selection."""
        if user_input is not None:
            return self.async_create_entry(
                title="WattWatch",
                data={},
                options={
                    CONF_ENTITIES: self._entities,
                    CONF_WINDOW_SIZE: int(self._options_input[CONF_WINDOW_SIZE]),
                    CONF_THRESHOLD: float(self._options_input[CONF_THRESHOLD]),
                    CONF_COOLDOWN: int(self._options_input[CONF_COOLDOWN]),
                    CONF_MIN_SAMPLES: int(self._options_input[CONF_MIN_SAMPLES]),
                    CONF_MIN_DEVIATION: float(
                        self._options_input[CONF_MIN_DEVIATION]
                    ),
                    CONF_CONSECUTIVE_REQUIRED: int(
                        self._options_input[CONF_CONSECUTIVE_REQUIRED]
                    ),
                    CONF_MONITOR_DIRECTIONS: {
                        entity_id: user_input[entity_id]
                        for entity_id in self._entities
                    },
                },
            )

        schema = _build_directions_schema(self._entities)
        return self.async_show_form(
            step_id="directions",
            data_schema=schema,
            description_placeholders={
                "entities": ", ".join(
                    e.split(".")[-1] for e in self._entities
                )
            },
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> WattWatchOptionsFlow:
        """Get the options flow handler."""
        return WattWatchOptionsFlow(config_entry)


class WattWatchOptionsFlow(OptionsFlow):
    """Handle options flow for WattWatch."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._entities: list[str] = []
        self._settings: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle entity selection and global settings."""
        if user_input is not None:
            self._entities = user_input[CONF_ENTITIES]
            self._settings = {
                CONF_WINDOW_SIZE: int(user_input[CONF_WINDOW_SIZE]),
                CONF_THRESHOLD: float(user_input[CONF_THRESHOLD]),
                CONF_COOLDOWN: int(user_input[CONF_COOLDOWN]),
                CONF_MIN_SAMPLES: int(user_input[CONF_MIN_SAMPLES]),
                CONF_MIN_DEVIATION: float(user_input[CONF_MIN_DEVIATION]),
                CONF_CONSECUTIVE_REQUIRED: int(
                    user_input[CONF_CONSECUTIVE_REQUIRED]
                ),
            }
            return await self.async_step_directions()

        current = self._config_entry.options

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENTITIES,
                    default=current.get(CONF_ENTITIES, []),
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain="sensor",
                        device_class="power",
                        multiple=True,
                    )
                ),
                vol.Required(
                    CONF_WINDOW_SIZE,
                    default=current.get(CONF_WINDOW_SIZE, DEFAULT_WINDOW_SIZE),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=10, max=1000, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_THRESHOLD,
                    default=current.get(CONF_THRESHOLD, DEFAULT_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1.0, max=10.0, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_COOLDOWN,
                    default=current.get(CONF_COOLDOWN, DEFAULT_COOLDOWN),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=3600, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_MIN_SAMPLES,
                    default=current.get(CONF_MIN_SAMPLES, DEFAULT_MIN_SAMPLES),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=3, max=50, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_MIN_DEVIATION,
                    default=current.get(
                        CONF_MIN_DEVIATION, DEFAULT_MIN_DEVIATION
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0.0, max=1000.0, step=0.1, mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(
                    CONF_CONSECUTIVE_REQUIRED,
                    default=current.get(
                        CONF_CONSECUTIVE_REQUIRED, DEFAULT_CONSECUTIVE_REQUIRED
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=20, step=1, mode=NumberSelectorMode.BOX
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )

    async def async_step_directions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle per-entity direction selection in options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self._settings,
                    CONF_ENTITIES: self._entities,
                    CONF_MONITOR_DIRECTIONS: {
                        entity_id: user_input[entity_id]
                        for entity_id in self._entities
                    },
                }
            )

        current_directions = self._config_entry.options.get(
            CONF_MONITOR_DIRECTIONS, {}
        )
        schema = _build_directions_schema(self._entities, current_directions)

        return self.async_show_form(
            step_id="directions",
            data_schema=schema,
            description_placeholders={
                "entities": ", ".join(
                    e.split(".")[-1] for e in self._entities
                )
            },
        )
