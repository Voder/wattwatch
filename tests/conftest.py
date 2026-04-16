"""Test configuration for WattWatch."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock homeassistant and voluptuous before any wattwatch imports
# so tests can run without the full HA environment
ha_mock = MagicMock()
sys.modules["homeassistant"] = ha_mock
sys.modules["homeassistant.config_entries"] = ha_mock
sys.modules["homeassistant.const"] = ha_mock
sys.modules["homeassistant.core"] = ha_mock
sys.modules["homeassistant.helpers"] = ha_mock
sys.modules["homeassistant.helpers.event"] = ha_mock
sys.modules["homeassistant.helpers.storage"] = ha_mock
sys.modules["homeassistant.helpers.selector"] = ha_mock
sys.modules["homeassistant.helpers.entity_platform"] = ha_mock
sys.modules["homeassistant.components"] = ha_mock
sys.modules["homeassistant.components.binary_sensor"] = ha_mock
sys.modules["homeassistant.components.sensor"] = ha_mock
sys.modules["voluptuous"] = MagicMock()

# Add custom_components to path
sys.path.insert(0, str(Path(__file__).parent.parent))
