# WattWatch

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

Home Assistant custom integration for detecting anomalies in power consumption. Monitors selected power sensor entities and alerts when consumption is abnormally high or low.

## Features

- **Z-score anomaly detection** with configurable sliding window
- **Binary sensors** per monitored entity (ON = anomaly active)
- **Events** (`wattwatch_anomaly_detected`) for automation triggers with detailed data
- **Diagnostic sensors** showing z-score, running mean, and standard deviation
- **Persistence** across HA restarts — detection works immediately after reboot
- **No external dependencies** — uses only Python standard library
- **Configurable** via UI — entity selection, sensitivity, cooldown

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations**
3. Click the three dots menu, select **Custom repositories**
4. Add this repository URL, category: **Integration**
5. Click **Install**
6. Restart Home Assistant

### Manual

1. Copy `custom_components/wattwatch/` to your `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **Add Integration**, search for **WattWatch**
3. Select power sensor entities to monitor
4. Configure detection parameters:
   - **Window size** (default: 100) — number of samples in the sliding window
   - **Z-score threshold** (default: 3.0) — standard deviations from mean to trigger anomaly
   - **Cooldown** (default: 60s) — minimum seconds between event firings per entity
   - **Minimum samples** (default: 10) — samples needed before detection activates

## How It Works

WattWatch uses a **z-score algorithm** with a sliding window:

1. Each power reading is compared against the mean and standard deviation of recent readings
2. If the reading deviates more than the configured threshold (in standard deviations), it's flagged as an anomaly
3. **Spikes** (abnormally high) and **drops** (abnormally low) are detected separately
4. Anomalous values are included in the window so the detector adapts to legitimate step changes

## Entities Created

For each monitored power entity, WattWatch creates:

| Entity | Type | Description |
|--------|------|-------------|
| `binary_sensor.wattwatch_<name>_anomaly` | Binary Sensor | ON when anomaly detected |
| `sensor.wattwatch_<name>_z_score` | Sensor (diagnostic) | Current z-score |
| `sensor.wattwatch_<name>_mean` | Sensor (diagnostic) | Running mean (W) |
| `sensor.wattwatch_<name>_stdev` | Sensor (diagnostic) | Running standard deviation (W) |

## Automation Examples

### Binary sensor trigger

```yaml
automation:
  - alias: "Alert on power anomaly"
    trigger:
      - platform: state
        entity_id: binary_sensor.wattwatch_dryer_power_anomaly
        to: "on"
    action:
      - service: notify.notify
        data:
          message: >
            Power anomaly detected on dryer:
            {{ state_attr('binary_sensor.wattwatch_dryer_power_anomaly', 'current_value') }}W
            (expected: {{ state_attr('binary_sensor.wattwatch_dryer_power_anomaly', 'expected_value') }}W)
```

### Event trigger (richer data)

```yaml
automation:
  - alias: "Alert on power spike"
    trigger:
      - platform: event
        event_type: wattwatch_anomaly_detected
        event_data:
          anomaly_type: spike
    action:
      - service: notify.notify
        data:
          message: >
            Power spike on {{ trigger.event.data.entity_id }}:
            {{ trigger.event.data.current_value }}W
            (z-score: {{ trigger.event.data.z_score }})
```

### Filter by entity

```yaml
automation:
  - alias: "Fridge power drop alert"
    trigger:
      - platform: event
        event_type: wattwatch_anomaly_detected
        event_data:
          entity_id: sensor.fridge_power
          anomaly_type: drop
    action:
      - service: notify.notify
        data:
          message: "Fridge power dropped — may have stopped running!"
```

## Tuning Sensitivity

- **Lower threshold** (e.g., 2.0) = more sensitive, more alerts
- **Higher threshold** (e.g., 5.0) = less sensitive, fewer false positives
- **Larger window** (e.g., 500) = considers more history, slower to adapt
- **Smaller window** (e.g., 20) = adapts faster, may miss gradual trends

Use the diagnostic sensors (z-score, mean, stdev) to understand your power patterns and tune accordingly.

## License

MIT
