import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from replay_review_package import verify_archive
from verify_export_v2 import check_source_pool


def make_archive(path, names=None, bad_hash=False):
    payload = b"fixture"
    files = names or {"docs/example.md": payload}
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    if bad_hash:
        hashes[next(iter(hashes))] = "0" * 64
    with zipfile.ZipFile(path, "w") as bundle:
        for name, value in files.items():
            bundle.writestr(name, value)
        bundle.writestr("manifest.json", json.dumps({"files_sha256": hashes}))


def test_archive_manifest_integrity(tmp_path):
    archive = tmp_path / "valid.zip"
    make_archive(archive)
    assert verify_archive(archive)["files_checked"] == 1
    make_archive(archive, bad_hash=True)
    with pytest.raises(ValueError, match="hash"):
        verify_archive(archive)


@pytest.mark.parametrize("name", ["../outside", "C:/outside", "docs\\outside", "/absolute"])
def test_unsafe_zip_names_rejected(tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    make_archive(archive, {name: b"fixture"})
    with pytest.raises(ValueError, match="Unsafe"):
        verify_archive(archive)


def test_zip_unlisted_file_rejected(tmp_path):
    archive = tmp_path / "extra.zip"
    make_archive(archive)
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("unexpected.txt", b"extra")
    with pytest.raises(ValueError, match="manifest"):
        verify_archive(archive)


def test_source_hashes_and_training_candidate_boundary(tmp_path):
    raw, abstract = b"real-test-fixture-atom", "Fixture abstract"
    (tmp_path / "response.atom").write_bytes(raw)
    row = {"abstract": abstract, "content_hash": hashlib.sha256(abstract.encode()).hexdigest(),
           "raw_response_sha256": hashlib.sha256(raw).hexdigest(), "title_match": True,
           "reference_provider": "arXiv", "ner_annotations": None,
           "policy": {"license": "CC0-1.0"}}
    (tmp_path / "abstracts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (tmp_path / "request.json").write_text(json.dumps({"intended_split": "train_candidates_only"}), encoding="utf-8")
    result = check_source_pool(tmp_path)
    assert result["records"] == 1 and result["hashes_verified"] and result["candidate_boundary_verified"]
    row["ner_annotations"] = []
    (tmp_path / "abstracts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert not check_source_pool(tmp_path)["candidate_boundary_verified"]
    row["abstract"] = "tampered"
    (tmp_path / "abstracts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert not check_source_pool(tmp_path)["hashes_verified"]


def test_legacy_source_requires_explicit_bound_scope_sidecar(tmp_path):
    raw, abstract = b"source-fixture", "Original fixture"
    (tmp_path / "response.atom").write_bytes(raw)
    row = {"abstract": abstract, "content_hash": hashlib.sha256(abstract.encode()).hexdigest(),
           "raw_response_sha256": hashlib.sha256(raw).hexdigest(), "title_match": True,
           "ner_annotations": None, "policy": {"license": "CC0-1.0"}}
    (tmp_path / "abstracts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (tmp_path / "request.json").write_text("{}", encoding="utf-8")
    assert not check_source_pool(tmp_path)["candidate_boundary_verified"]
    scope = {"intended_split": "train_candidates_only", "reference_provider": "DBLP",
             "bound_files_sha256": {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                                    for name in ("abstracts.jsonl", "request.json")}}
    (tmp_path / "scope_policy.json").write_text(json.dumps(scope), encoding="utf-8")
    result = check_source_pool(tmp_path)
    assert result["candidate_boundary_verified"] and result["reference_providers"] == ["DBLP"]
    assert result["scope_source"] == "scope_policy.json"
    (tmp_path / "request.json").write_text('{"tampered": true}', encoding="utf-8")
    assert not check_source_pool(tmp_path)["candidate_boundary_verified"]
