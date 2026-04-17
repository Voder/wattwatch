"""Constants for WattWatch integration."""

from homeassistant.const import Platform

DOMAIN = "wattwatch"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

# Events
EVENT_ANOMALY_DETECTED = "wattwatch_anomaly_detected"

# Configuration keys
CONF_ENTITIES = "entities"
CONF_WINDOW_SIZE = "window_size"
CONF_THRESHOLD = "threshold"
CONF_COOLDOWN = "cooldown"
CONF_MIN_SAMPLES = "min_samples"

# Defaults
DEFAULT_WINDOW_SIZE = 100
DEFAULT_THRESHOLD = 3.0
DEFAULT_COOLDOWN = 60
DEFAULT_MIN_SAMPLES = 10

# Storage
STORAGE_KEY = "wattwatch_window_data"
STORAGE_VERSION = 1

# Anomaly types
ANOMALY_TYPE_SPIKE = "spike"
ANOMALY_TYPE_DROP = "drop"

# Diagnostic sensor types
DIAGNOSTIC_SENSOR_TYPES = ("z_score", "mean", "stdev")

# Monitor direction
CONF_MONITOR_DIRECTIONS = "monitor_directions"
DIRECTION_BOTH = "both"
DIRECTION_HIGH = "high"
DIRECTION_LOW = "low"
DEFAULT_DIRECTION = DIRECTION_BOTH
