"""Job discovery functions."""

from .incruit_rss import (
    IncruitRssParseError,
    build_incruit_discovery_record,
    build_incruit_discovery_records,
)
from .incruit_feed import IncruitFeedError, fetch_incruit_rss
from .greenhouse_board import (
    GreenhouseBoardParseError,
    build_greenhouse_discovery_records,
)
from .store import (
    DiscoveryStoreError,
    load_discovery_records,
    merge_discovery_records,
)
from .service import run_greenhouse_discovery, run_incruit_discovery
from .report import format_discovery_records

__all__ = [
    "IncruitRssParseError",
    "build_incruit_discovery_record",
    "build_incruit_discovery_records",
    "IncruitFeedError",
    "fetch_incruit_rss",
    "GreenhouseBoardParseError",
    "build_greenhouse_discovery_records",
    "DiscoveryStoreError",
    "load_discovery_records",
    "merge_discovery_records",
    "run_incruit_discovery",
    "run_greenhouse_discovery",
    "format_discovery_records",
]
