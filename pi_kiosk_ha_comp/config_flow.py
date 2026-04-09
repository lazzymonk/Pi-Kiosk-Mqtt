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

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_name: str | None = None
        self._discovered_prefix: str | None = None

    async def async_step_user(self, user_input=None):
        """Handle the manual setup step."""
        errors = {}

        if user_input is not None:
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

    async def async_step_mqtt(self, discovery_info):
        """Handle auto-discovery from MQTT."""
        topic_prefix = discovery_info[CONF_TOPIC_PREFIX]
        hostname = discovery_info.get(CONF_NAME, "Pi Kiosk")

        await self.async_set_unique_id(topic_prefix)
        self._abort_if_unique_id_configured()

        self._discovered_name = hostname
        self._discovered_prefix = topic_prefix

        # Set a nice title for the discovery notification
        self.context["title_placeholders"] = {"name": hostname}

        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        """Ask user to confirm adding the discovered kiosk."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, self._discovered_name),
                data={
                    CONF_NAME: user_input.get(CONF_NAME, self._discovered_name),
                    CONF_TOPIC_PREFIX: self._discovered_prefix,
                },
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME, default=self._discovered_name
                    ): str,
                }
            ),
            description_placeholders={
                "hostname": self._discovered_name,
                "topic_prefix": self._discovered_prefix,
            },
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
