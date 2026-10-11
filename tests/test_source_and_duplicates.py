import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_abstract_pilot import parse_feed
from find_near_duplicates import suggest_pairs


def test_api_id_title_hash_and_license():
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2412.20086v1</id><title>Same Title</title><summary>Real fixture abstract.</summary></entry></feed>'
    rows = parse_feed(feed, {"2412.20086": {"publicationId": "journals/corr/abs-2412-20086", "title": "Same Title."}}, "https://export.arxiv.org/api/query", "2026-10-05T10:00:00Z")
    assert rows[0]["title_match"] and rows[0]["policy"]["license"] == "CC0-1.0"
    assert len(rows[0]["content_hash"]) == 64
    assert rows[0]["ner_annotations"] is None


@pytest.mark.parametrize("payload", [b'<html>error</html>', b'<!DOCTYPE feed><feed/>'])
def test_api_rejects_non_atom_or_entities(payload):
    with pytest.raises(ValueError):
        parse_feed(payload, {}, "test", "test")


def test_title_mismatch_stays_unverified():
    feed = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/2412.20086</id><title>Different</title><summary>A.</summary></entry></feed>'
    rows = parse_feed(feed, {"2412.20086": {"publicationId": "x", "title": "Original"}}, "test", "test")
    assert rows[0]["status"] == "title_mismatch_needs_review"


def test_reordered_title_candidates_not_auto_merged():
    rows = [{"publicationId": "a", "text": "Xylophone: A Neural Approach for Unusual Tasks", "year": 2020, "groupId": "a"},
            {"publicationId": "b", "text": "A Neural Approach for Unusual Tasks: Xylophone", "year": 2021, "groupId": "b"},
            {"publicationId": "c", "text": "Xylophone: A Neural Approach for Unusual Tasks", "year": 2020, "groupId": "a"}]
    pairs, summary = suggest_pairs(rows)
    assert any(r["leftId"] == "a" and r["rightId"] == "b" for r in pairs)
    assert not any(r["leftId"] == "a" and r["rightId"] == "c" for r in pairs)
    assert not summary["groups_changed"] and not summary["human_review_complete"]
