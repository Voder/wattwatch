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
CONF_MIN_DEVIATION = "min_deviation"
CONF_CONSECUTIVE_REQUIRED = "consecutive_required"

# Defaults
DEFAULT_WINDOW_SIZE = 100
DEFAULT_THRESHOLD = 3.0
DEFAULT_COOLDOWN = 60
DEFAULT_MIN_SAMPLES = 10
DEFAULT_MIN_DEVIATION = 5.0
DEFAULT_CONSECUTIVE_REQUIRED = 3

# Storage
STORAGE_KEY = "wattwatch_window_data"
STORAGE_VERSION = 1

# Anomaly types — non-cyclic fallback
ANOMALY_TYPE_SPIKE = "spike"
ANOMALY_TYPE_DROP = "drop"

# Anomaly types — cyclic mode
ANOMALY_TYPE_STUCK_ON = "stuck_on"
ANOMALY_TYPE_STUCK_OFF = "stuck_off"
ANOMALY_TYPE_POWER_SPIKE = "power_spike"
ANOMALY_TYPE_POWER_DROP = "power_drop"

# Direction-grouped sets (used by coordinator direction filter)
ANOMALY_TYPES_HIGH = {ANOMALY_TYPE_SPIKE, ANOMALY_TYPE_STUCK_ON, ANOMALY_TYPE_POWER_SPIKE}
ANOMALY_TYPES_LOW = {ANOMALY_TYPE_DROP, ANOMALY_TYPE_STUCK_OFF, ANOMALY_TYPE_POWER_DROP}

# Diagnostic sensor types
DIAGNOSTIC_SENSOR_TYPES = ("z_score", "mean", "stdev")

# Monitor direction
CONF_MONITOR_DIRECTIONS = "monitor_directions"
DIRECTION_BOTH = "both"
DIRECTION_HIGH = "high"
DIRECTION_LOW = "low"
DEFAULT_DIRECTION = DIRECTION_BOTH
