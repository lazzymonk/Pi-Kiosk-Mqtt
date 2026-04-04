"""Config flow for Pi Kiosk integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TOPIC_PREFIX,
    DEFAULT_NAME,
    DEFAULT_TOPIC_PREFIX,
)


class PiKioskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pi Kiosk."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Check if this topic prefix is already configured
            await self.async_set_unique_id(user_input[CONF_TOPIC_PREFIX])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return PiKioskOptionsFlow(config_entry)


class PiKioskOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Pi Kiosk."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TOPIC_PREFIX,
                        default=self.config_entry.data.get(
                            CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX
                        ),
                    ): str,
                }
            ),
        )
