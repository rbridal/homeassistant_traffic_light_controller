"""Entry point for the Shop Traffic Light service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .mqtt import TrafficLightMQTT
from .relay import RelayController

logger = logging.getLogger("traffic_light")


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


async def async_main(config_path: Path) -> None:
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)

    setup_logging(cfg.get("logging", {}).get("level", "INFO"))

    mqtt_cfg = cfg["mqtt"]
    i2c_cfg = cfg["i2c"]
    relays_cfg = cfg["relays"]
    disc_cfg = cfg["discovery"]

    relay = RelayController(
        bus_number=i2c_cfg.get("bus", 1),
        address=i2c_cfg.get("address", 0x10),
        green_reg=relays_cfg.get("green", 0x01),
        yellow_reg=relays_cfg.get("yellow", 0x02),
        red_reg=relays_cfg.get("red", 0x03),
    )

    mqtt = TrafficLightMQTT(
        host=mqtt_cfg["host"],
        port=int(mqtt_cfg["port"]),
        username=mqtt_cfg["username"],
        password=mqtt_cfg["password"],
        client_id=mqtt_cfg.get("client_id", "traffic-light-control"),
        device_name=disc_cfg.get("device_name", "Shop Traffic Light"),
        device_id=disc_cfg.get("device_id", "shop_traffic_light"),
        manufacturer=disc_cfg.get("manufacturer", "Custom"),
        model=disc_cfg.get("model", "DockerPi EP-0099 Traffic Light"),
        options=disc_cfg.get("options"),
        relay=relay,
    )

    # Open hardware
    try:
        relay.open()
        # Start in a known safe state
        relay.set_mode("off")
    except Exception:
        logger.exception("Failed to initialize relay hardware")
        sys.exit(1)

    # Graceful shutdown handling
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()
        mqtt.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("Starting Shop Traffic Light service")

    mqtt_task = asyncio.create_task(mqtt.run())

    await stop_event.wait()

    logger.info("Shutting down...")
    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        pass

    relay.close()
    logger.info("Shutdown complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shop Traffic Light MQTT controller")
    parser.add_argument(
        "-c",
        "--config",
        default="/opt/traffic-light-control/config.yaml",
        help="Path to config.yaml",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    try:
        asyncio.run(async_main(config_path))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
