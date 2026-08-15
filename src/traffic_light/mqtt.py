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

    async def _publish_discovery(self, client: Client) -> None:
        payload = json.dumps(self._discovery_payload())
        await client.publish(
            self.discovery_topic,
            payload,
            qos=1,
            retain=True,
        )
        logger.info("Published MQTT discovery config")

    async def _publish_availability(self, client: Client, online: bool) -> None:
        payload = AVAILABILITY_ONLINE if online else AVAILABILITY_OFFLINE
        await client.publish(
            self.availability_topic,
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
