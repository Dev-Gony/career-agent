"""Validated local configuration for external career sources."""

from .greenhouse_boards import (
    GreenhouseBoardConfigError,
    load_enabled_greenhouse_board,
    load_enabled_greenhouse_boards,
)

__all__ = [
    "GreenhouseBoardConfigError",
    "load_enabled_greenhouse_board",
    "load_enabled_greenhouse_boards",
]
