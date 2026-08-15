# Shop Traffic Light Control

Modern MQTT-based controller for a Raspberry Pi + DockerPi 4 Channel Relay (EP-0099) traffic light used with Home Assistant.

The service publishes Home Assistant MQTT Discovery so the traffic light appears as a proper **device** with a `select` entity.

## Features

- Clean MQTT + MQTT Discovery integration (no more helper entities / WebSocket token)
- Proper I2C control via `smbus2` (no more `i2cset` subprocesses)
- Automatic reconnection
- Availability reporting
- Graceful shutdown (turns lights off)
- Simple YAML configuration
- Systemd service with hardening

## Hardware

- Raspberry Pi (any model with I2C)
- DockerPi 4 Channel Relay HAT (EP-0099) at address `0x10`
- Mapping:
  - Green  → register `0x01`
  - Yellow → register `0x02`
  - Red    → register `0x03`

## Requirements

- Python 3.10+
- Home Assistant with Mosquitto broker (or any MQTT broker)
- `i2c` enabled on the Pi (`sudo raspi-config`)

## Installation on the Raspberry Pi

```bash
# 1. Create the install directory
sudo mkdir -p /opt/traffic-light-control
sudo chown rbridal:rbridal /opt/traffic-light-control

# 2. Copy the project files into /opt/traffic-light-control
#    (or git clone this repo)

cd /opt/traffic-light-control

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create config
cp config.example.yaml config.yaml
nano config.yaml          # put your real MQTT password, etc.

# 6. Install the systemd unit
sudo cp systemd/traffic-light-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now traffic-light-control.service

# 7. Check status
systemctl status traffic-light-control.service
journalctl -u traffic-light-control.service -f
```

## Home Assistant

After the service starts you should see a new device:

**Settings → Devices & Services → MQTT → Shop Traffic Light**

Entity: `select.shop_traffic_light`  
Options: `off`, `red`, `yellow`, `green`, `all`

### Updating your existing automation

Replace every occurrence of:

```yaml
entity_id: input_select.shop_traffic_light
```

with:

```yaml
entity_id: select.shop_traffic_light
```

and change the action from `input_select.select_option` to `select.select_option`.

You can then delete the old `input_select.shop_traffic_light` helper.

## Development / testing

```bash
cd /opt/traffic-light-control
source venv/bin/activate
python -m traffic_light.main -c config.yaml
```

## License

MIT (or whatever you prefer)
