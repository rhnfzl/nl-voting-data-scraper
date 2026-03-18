"""nl-voting-data-scraper: Scrape Dutch voting advice (StemWijzer) data for any election."""

__version__ = "0.3.0"

from nl_voting_data_scraper.config import KNOWN_ELECTIONS, ElectionConfig
from nl_voting_data_scraper.models import (
    ElectionData,
    ElectionIndexEntry,
    Party,
    PartyPosition,
    Statement,
    VotematchMeta,
)
from nl_voting_data_scraper.scraper import StemwijzerScraper

__all__ = [
    "KNOWN_ELECTIONS",
    "ElectionConfig",
    "ElectionData",
    "ElectionIndexEntry",
    "Party",
    "PartyPosition",
    "Statement",
    "StemwijzerScraper",
    "VotematchMeta",
]
