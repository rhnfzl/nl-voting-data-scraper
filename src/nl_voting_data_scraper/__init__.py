"""nl-voting-data-scraper: Scrape Dutch voting advice (StemWijzer) data for any election."""

__version__ = "0.2.0"

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
    "ElectionData",
    "ElectionIndexEntry",
    "Party",
    "PartyPosition",
    "Statement",
    "StemwijzerScraper",
    "VotematchMeta",
]
