"""Constants for the Pi Kiosk integration."""

DOMAIN = "pi_kiosk"

CONF_TOPIC_PREFIX = "topic_prefix"
CONF_NAME = "name"

DEFAULT_TOPIC_PREFIX = "kiosk"
DEFAULT_NAME = "Pi Kiosk"

# MQTT topics (appended to prefix)
TOPIC_REFRESH = "refresh"
TOPIC_SCREEN = "screen"
TOPIC_BRIGHTNESS = "brightness"
TOPIC_URL = "url"
TOPIC_STATUS = "status"
TOPIC_REBOOT = "reboot"
TOPIC_STATUS_RESPONSE = "status/response"
