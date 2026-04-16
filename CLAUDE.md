# WattWatch

Home Assistant custom integration for power consumption anomaly detection. HACS-installable. No external dependencies.

## Project Layout

```
custom_components/wattwatch/   # Integration source
tests/                         # Unit tests (pytest, no HA runtime required)
hacs.json                      # HACS metadata
```

## Architecture

**Event-driven** — subscribes to HA `state_changed` events via `async_track_state_change_event`. No polling.

| File | Role |
|------|------|
| `anomaly.py` | Z-score detector with sliding window. Pure Python, no HA imports. |
| `coordinator.py` | Central orchestrator — wires state changes → detection → entity updates + event firing |
| `__init__.py` | Integration lifecycle: setup, unload, options reload |
| `config_flow.py` | Config + options flow using `ConfigFlow` / `OptionsFlow` |
| `binary_sensor.py` | One `BinarySensorEntity` (PROBLEM class) per monitored entity |
| `sensor.py` | Diagnostic sensors: z-score, running mean, running stdev |
| `const.py` | All constants and defaults |

## Key Concepts

**Anomaly detection**: Z-score with configurable sliding window (`deque`, default 100 samples). Anomalous values are included in the window — allows adaptation to legitimate step changes.

**Outputs**:
- Binary sensors: `binary_sensor.wattwatch_<name>_anomaly` (ON = anomaly active)
- Event: `wattwatch_anomaly_detected` (fields: `entity_id`, `current_value`, `expected_value`, `z_score`, `anomaly_type`, `stdev`)

**Persistence**: `homeassistant.helpers.storage.Store` saves window data every 5 min + on shutdown. Restores on startup.

**Cooldown**: Event firing throttled per entity (default 60s). Binary sensor state ignores cooldown — always reflects truth.

## Commands

```bash
# Run tests
PYTHONPATH=. python3 -m pytest tests/ -v

# Syntax check all modules
python3 -m py_compile custom_components/wattwatch/*.py
```

Tests run without HA installed — `tests/conftest.py` mocks all `homeassistant.*` imports.

## Configuration Defaults

| Key | Default | Description |
|-----|---------|-------------|
| `window_size` | 100 | Sliding window sample count |
| `threshold` | 3.0 | Z-score standard deviations to trigger |
| `cooldown` | 60 | Seconds between event firings per entity |
| `min_samples` | 10 | Samples before detection activates |

## Adding Features

- **New detection algorithm**: Add class to `anomaly.py`, wire in `coordinator.py`
- **New entity type**: New platform file, add to `PLATFORMS` in `const.py`, forward in `__init__.py`
- **Per-entity overrides**: Add `CONF_ENTITY_OVERRIDES` to `const.py`, options flow second step, apply in `coordinator._build_detector()`

## HA Compatibility

Minimum: `2024.12.0`. Uses `entry.runtime_data` (requires 2024.x+).
