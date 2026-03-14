"""Tests for Pydantic data models."""

from nl_voting_data_scraper.models import (
    ElectionData,
    ElectionIndexEntry,
    Party,
    Statement,
)


class TestStatement:
    def test_parse_plain_title(self):
        s = Statement(id=1, theme="test", title="Plain title", index=0)
        assert s.title == "Plain title"
        assert s.isShootout is False

    def test_parse_rich_title(self):
        rich_title = [
            "De inwoners moeten via een ",
            {"text": "referendum", "information": "Volksraadpleging"},
            ".",
        ]
        s = Statement(id=1, theme="test", title=rich_title, index=0)
        assert isinstance(s.title, list)
        assert len(s.title) == 3

    def test_shootout_flag(self):
        s = Statement(id=1, theme="t", title="t", index=0, isShootout=True)
        assert s.isShootout is True


class TestParty:
    def test_parse_party(self, sample_municipality):
        raw_party = sample_municipality["parties"][0]
        party = Party.model_validate(raw_party)
        assert party.id > 0
        assert party.name
        assert len(party.statements) > 0

    def test_party_positions(self, sample_municipality):
        raw_party = sample_municipality["parties"][0]
        party = Party.model_validate(raw_party)
        for pos in party.statements:
            assert pos.position in ("agree", "disagree", "neither")


class TestElectionData:
    def test_parse_full(self, sample_municipality):
        data = ElectionData.model_validate(sample_municipality)
        assert len(data.parties) > 0
        assert len(data.statements) > 0
        assert data.votematch.name
        assert data.votematch.remote_id.startswith("GM")

    def test_votematch_meta(self, sample_municipality):
        data = ElectionData.model_validate(sample_municipality)
        vm = data.votematch
        assert vm.context == "2026GR"
        assert vm.langcode == "nl"

    def test_roundtrip_json(self, sample_municipality):
        data = ElectionData.model_validate(sample_municipality)
        dumped = data.model_dump(by_alias=True)
        reparsed = ElectionData.model_validate(dumped)
        assert reparsed.votematch.id == data.votematch.id
        assert len(reparsed.parties) == len(data.parties)


class TestElectionIndexEntry:
    def test_parse_entry(self, sample_index):
        for raw in sample_index:
            entry = ElectionIndexEntry.model_validate(raw)
            assert entry.id > 0
            assert entry.remoteId.startswith("GM")
            assert entry.language in ("nl", "en", "fy")

    def test_decrypt_flag(self, sample_index):
        for raw in sample_index:
            entry = ElectionIndexEntry.model_validate(raw)
            assert entry.decrypt is True
