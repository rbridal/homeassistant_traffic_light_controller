"""MQTT client with Home Assistant discovery support."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

from aiomqtt import Client, MqttError, Will

from .constants import (
    AVAILABILITY_OFFLINE,
    AVAILABILITY_ONLINE,
    DISCOVERY_PREFIX,
)
from .relay import Mode, RelayController

logger = logging.getLogger(__name__)


class TrafficLightMQTT:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        client_id: str = "traffic-light-control",
        device_name: str = "Shop Traffic Light",
        device_id: str = "shop_traffic_light",
        manufacturer: str = "Custom",
        model: str = "DockerPi EP-0099 Traffic Light",
        options: list[str] | None = None,
        relay: RelayController,
        on_mode_change: Callable[[Mode], Awaitable[None]] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id

        self.device_name = device_name
        self.device_id = device_id
        self.manufacturer = manufacturer
        self.model = model
        self.options = options or ["off", "red", "yellow", "green", "all"]

        self.relay = relay
        self.on_mode_change = on_mode_change

        # Topics
        self.base = f"{DISCOVERY_PREFIX}/select/{self.device_id}"
        self.command_topic = f"{self.base}/set"
        self.state_topic = f"{self.base}/state"
        self.availability_topic = f"{self.base}/availability"
        self.discovery_topic = f"{self.base}/config"

        # Binary sensor for online status
        self.online_base = f"{DISCOVERY_PREFIX}/binary_sensor/{self.device_id}_online"
        self.online_state_topic = f"{self.online_base}/state"
        self.online_discovery_topic = f"{self.online_base}/config"

        # Individual read-only light entities
        self.light_colors = ("red", "yellow", "green")
        self.light_state_topics = {
            color: f"{DISCOVERY_PREFIX}/light/{self.device_id}_{color}/state"
            for color in self.light_colors
        }
        self.light_discovery_topics = {
            color: f"{DISCOVERY_PREFIX}/light/{self.device_id}_{color}/config"
            for color in self.light_colors
        }

        self._client: Client | None = None
        self._stop = asyncio.Event()

    def _device_info(self) -> dict[str, Any]:
        return {
            "identifiers": [self.device_id],
            "name": self.device_name,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "sw_version": "1.0.0",
        }

    def _discovery_payload(self) -> dict[str, Any]:
        return {
            "name": self.device_name,
            "unique_id": f"{self.device_id}_select",
            "command_topic": self.command_topic,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "options": self.options,
            "device": self._device_info(),
            "icon": "mdi:traffic-light",
            "retain": True,
        }

    def _online_discovery_payload(self) -> dict[str, Any]:
        return {
            "name": f"{self.device_name} Online",
            "unique_id": f"{self.device_id}_online",
            "state_topic": self.online_state_topic,
            "payload_on": AVAILABILITY_ONLINE,
            "payload_off": AVAILABILITY_OFFLINE,
            "availability_topic": self.availability_topic,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device_class": "connectivity",
            "entity_category": "diagnostic",
            "device": self._device_info(),
            "icon": "mdi:lan-connect",
            "retain": True,
        }

    def _light_discovery_payload(self, color: str) -> dict[str, Any]:
        """Read-only light entity for a single color."""
        icons = {
            "red": "mdi:circle",
            "yellow": "mdi:circle",
            "green": "mdi:circle",
        }
        return {
            "name": f"{self.device_name} {color.capitalize()}",
            "unique_id": f"{self.device_id}_{color}",
            "state_topic": self.light_state_topics[color],
            "payload_on": "ON",
            "payload_off": "OFF",
            "availability_topic": self.availability_topic,
            "payload_available": AVAILABILITY_ONLINE,
            "payload_not_available": AVAILABILITY_OFFLINE,
            "device": self._device_info(),
            "icon": icons.get(color, "mdi:circle"),
            "retain": True,
            # No command_topic → read-only
        }

    async def _publish_discovery(self, client: Client) -> None:
        # Select entity
        payload = json.dumps(self._discovery_payload())
        await client.publish(
            self.discovery_topic,
            payload,
            qos=1,
            retain=True,
        )

        # Online binary sensor
        online_payload = json.dumps(self._online_discovery_payload())
        await client.publish(
            self.online_discovery_topic,
            online_payload,
            qos=1,
            retain=True,
        )

        # Individual color lights (read-only)
        for color in self.light_colors:
            light_payload = json.dumps(self._light_discovery_payload(color))
            await client.publish(
                self.light_discovery_topics[color],
                light_payload,
                qos=1,
                retain=True,
            )

        logger.info(
            "Published MQTT discovery config (select + online sensor + 3 lights)"
        )

    async def _publish_availability(self, client: Client, online: bool) -> None:
        payload = AVAILABILITY_ONLINE if online else AVAILABILITY_OFFLINE
        await client.publish(
            self.availability_topic,
            payload,
            qos=1,
            retain=True,
        )
        # Also publish to the dedicated online binary_sensor state topic
        await client.publish(
            self.online_state_topic,
            payload,
            qos=1,
            retain=True,
        )

    async def _publish_state(self, client: Client, mode: Mode) -> None:
        await client.publish(
            self.state_topic,
            mode,
            qos=1,
            retain=True,
        )

        # Derive and publish individual light states
        active = {
            "red": mode in ("red", "all"),
            "yellow": mode in ("yellow", "all"),
            "green": mode in ("green", "all"),
        }
        for color, is_on in active.items():
            await client.publish(
                self.light_state_topics[color],
                "ON" if is_on else "OFF",
                qos=1,
                retain=True,
            )

        logger.debug("Published state: %s", mode)

    async def _handle_message(self, topic: str, payload: str) -> None:
        if topic != self.command_topic:
            return

        mode = payload.strip().lower()
        if mode not in self.options:
            logger.warning("Received invalid mode '%s', ignoring", mode)
            return

        logger.info("Command received: %s", mode)

        try:
            self.relay.set_mode(mode)  # type: ignore[arg-type]
            if self.on_mode_change:
                await self.on_mode_change(mode)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Failed to set mode %s", mode)
            return

        # Echo state back (in case something else is listening)
        if self._client:
            await self._publish_state(self._client, mode)  # type: ignore[arg-type]

    async def run(self) -> None:
        """Main MQTT loop with automatic reconnection."""
        will = Will(
            topic=self.availability_topic,
            payload=AVAILABILITY_OFFLINE,
            qos=1,
            retain=True,
        )

        while not self._stop.is_set():
            try:
                async with Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier=self.client_id,
                    will=will,
                ) as client:
                    self._client = client

                    await self._publish_discovery(client)
                    await self._publish_availability(client, True)

                    # Publish current hardware state
                    await self._publish_state(client, self.relay.current_mode)

                    # Subscribe to commands
                    await client.subscribe(self.command_topic, qos=1)
                    logger.info("Subscribed to %s", self.command_topic)

                    async for message in client.messages:
                        if self._stop.is_set():
                            break
                        payload = message.payload.decode("utf-8", errors="replace")
                        await self._handle_message(str(message.topic), payload)

            except MqttError as exc:
                logger.warning("MQTT error: %s – reconnecting in 5 s", exc)
                self._client = None
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in MQTT loop – reconnecting in 5 s")
                self._client = None
                await asyncio.sleep(5)

        # Clean shutdown – try to mark offline before exiting
        if self._client:
            try:
                await self._publish_availability(self._client, False)
            except Exception:
                pass
        self._client = None
        logger.info("MQTT client stopped")

    def stop(self) -> None:
        self._stop.set()
