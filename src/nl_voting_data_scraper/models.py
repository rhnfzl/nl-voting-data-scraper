"""Pydantic data models matching StemWijzer raw JSON format."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnnotatedText(BaseModel):
    """Inline annotation within a statement title (glossary term)."""

    text: str
    information: str = ""
    accessibility: dict[str, str] | None = None


# Statement titles can be plain strings or rich text with annotations.
# e.g. "De gemeente moet..." or ["De inwoners moeten via een ", {"text": "referendum", ...}, "."]
StatementTitle = str | list[str | AnnotatedText]


class MoreInfo(BaseModel):
    """Additional info for a statement (background, pro/con arguments)."""

    text: str = ""
    pro: str = ""
    con: str = ""


class Statement(BaseModel):
    """A policy statement / question in the voting advice tool."""

    id: int
    theme: str = ""
    themeId: str = Field(default="", alias="themeId")
    title: Any  # str | list[str | AnnotatedText] — use Any for robust parsing
    isShootout: bool = Field(default=False, alias="isShootout")
    index: int = 0
    moreInfo: MoreInfo | dict[str, str] | None = Field(default=None, alias="moreInfo")

    model_config = {"populate_by_name": True}


class PartyPosition(BaseModel):
    """A party's position on a specific statement."""

    id: int
    position: Literal["agree", "disagree", "neither"] = "neither"
    explanation: str = ""
    accessibility: dict[str, str] | None = None


class Party(BaseModel):
    """A political party with its positions on all statements."""

    id: int
    name: str
    fullName: str = Field(default="", alias="fullName")
    logo: str = ""
    logoIndex: int = Field(default=0, alias="logoIndex")
    participates: bool = True
    website: str = ""
    hasSeats: bool = Field(default=False, alias="hasSeats")
    statements: list[PartyPosition] = []
    shootoutStatements: list[PartyPosition] = Field(
        default_factory=list, alias="shootoutStatements"
    )
    index: int = 0

    model_config = {"populate_by_name": True}


class VotematchMeta(BaseModel):
    """Metadata from the votematch key in raw data."""

    id: int
    name: str
    context: str = ""
    date: str = ""
    remote_id: str = ""
    langcode: str = "nl"


class ElectionData(BaseModel):
    """Complete scraped data for one election/municipality."""

    parties: list[Party]
    statements: list[Statement]
    shootoutStatements: list[Statement] = Field(
        default_factory=list, alias="shootoutStatements"
    )
    votematch: VotematchMeta

    model_config = {"populate_by_name": True}


class ElectionIndexEntry(BaseModel):
    """Entry in an election index (list of available municipalities)."""

    id: int
    name: str
    source: str
    remoteId: str = Field(alias="remoteId")
    language: str = "nl"
    decrypt: bool = True

    model_config = {"populate_by_name": True}
