"""DockerPi 4 Channel Relay (EP-0099) control via smbus2."""

from __future__ import annotations

import logging
from typing import Literal

from smbus2 import SMBus

logger = logging.getLogger(__name__)

Mode = Literal["off", "red", "yellow", "green", "all"]


class RelayController:
    """Simple wrapper around the DockerPi relay HAT."""

    def __init__(
        self,
        bus_number: int = 1,
        address: int = 0x10,
        green_reg: int = 0x01,
        yellow_reg: int = 0x02,
        red_reg: int = 0x03,
    ) -> None:
        self.bus_number = bus_number
        self.address = address
        self.regs = {
            "green": green_reg,
            "yellow": yellow_reg,
            "red": red_reg,
        }
        self._bus: SMBus | None = None
        self._current_mode: Mode = "off"

    def open(self) -> None:
        if self._bus is None:
            self._bus = SMBus(self.bus_number)
            logger.info(
                "Opened I2C bus %s, device 0x%02x",
                self.bus_number,
                self.address,
            )

    def close(self) -> None:
        if self._bus is not None:
            try:
                self.set_mode("off")
            except Exception:
                logger.exception("Failed to turn relays off during close")
            self._bus.close()
            self._bus = None
            logger.info("Closed I2C bus")

    def _write(self, register: int, value: int) -> None:
        if self._bus is None:
            raise RuntimeError("RelayController is not open")
        self._bus.write_byte_data(self.address, register, value)

    def set_mode(self, mode: Mode) -> None:
        """Set the traffic light to the requested mode.

        Always writes the full desired state so the hardware matches
        exactly what we intend, regardless of previous state.
        """
        if mode not in ("off", "red", "yellow", "green", "all"):
            raise ValueError(f"Invalid mode: {mode}")

        states = {
            "red": 0x00,
            "yellow": 0x00,
            "green": 0x00,
        }

        if mode == "red":
            states["red"] = 0xFF
        elif mode == "yellow":
            states["yellow"] = 0xFF
        elif mode == "green":
            states["green"] = 0xFF
        elif mode == "all":
            states["red"] = 0xFF
            states["yellow"] = 0xFF
            states["green"] = 0xFF
        # "off" leaves everything 0x00

        for color, value in states.items():
            reg = self.regs[color]
            self._write(reg, value)

        self._current_mode = mode
        logger.info("Relays set to mode '%s'", mode)

    @property
    def current_mode(self) -> Mode:
        return self._current_mode

    def __enter__(self) -> "RelayController":
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()
