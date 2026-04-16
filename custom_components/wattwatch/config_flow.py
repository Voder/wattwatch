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
)

from .const import (
    CONF_COOLDOWN,
    CONF_ENTITIES,
    CONF_MIN_SAMPLES,
    CONF_THRESHOLD,
    CONF_WINDOW_SIZE,
    DEFAULT_COOLDOWN,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
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
    }
)


class WattWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WattWatch."""

    VERSION = 1

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
            return self.async_create_entry(
                title="WattWatch",
                data={},
                options={
                    CONF_ENTITIES: self._entities,
                    CONF_WINDOW_SIZE: int(user_input[CONF_WINDOW_SIZE]),
                    CONF_THRESHOLD: float(user_input[CONF_THRESHOLD]),
                    CONF_COOLDOWN: int(user_input[CONF_COOLDOWN]),
                    CONF_MIN_SAMPLES: int(user_input[CONF_MIN_SAMPLES]),
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=OPTIONS_SCHEMA,
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_ENTITIES: user_input[CONF_ENTITIES],
                    CONF_WINDOW_SIZE: int(user_input[CONF_WINDOW_SIZE]),
                    CONF_THRESHOLD: float(user_input[CONF_THRESHOLD]),
                    CONF_COOLDOWN: int(user_input[CONF_COOLDOWN]),
                    CONF_MIN_SAMPLES: int(user_input[CONF_MIN_SAMPLES]),
                }
            )

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
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
