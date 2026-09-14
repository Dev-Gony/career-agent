"""Validated local configuration for external career sources."""

from .greenhouse_boards import (
    GreenhouseBoardConfigError,
    load_enabled_greenhouse_board,
)

__all__ = [
    "GreenhouseBoardConfigError",
    "load_enabled_greenhouse_board",
]
