"""Restore byte-exact graph JSONL files from the published gzip companions."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/publication/large_assets.json").read_text(encoding="utf-8"))
    checked = 0
    for asset in manifest["assets"]:
        if asset["kind"] != "compressed_graph":
            continue
        target = (ROOT / asset["path"]).resolve()
        archive = (ROOT / asset["archive"]).resolve()
        if not target.is_relative_to(ROOT) or not archive.is_relative_to(ROOT):
            raise ValueError("Asset path escapes the repository")
        # Refuse to replace an existing file with different contents.
        if target.exists():
            with target.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if target.stat().st_size != asset["bytes"] or digest != asset["sha256"]:
                raise ValueError(f"Existing graph differs: {asset['path']}")
        elif not args.verify_only:
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
                digest = hashlib.sha256()
                size = 0
                try:
                    with gzip.open(archive, "rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                            size += len(chunk)
                            output.write(chunk)
                    if size != asset["bytes"] or digest.hexdigest() != asset["sha256"]:
                        raise ValueError(f"Archive integrity failed: {asset['archive']}")
                except BaseException:
                    output.close()
                    temporary.unlink(missing_ok=True)
                    raise
            try:
                # Hard-link publication is atomic and refuses an existing target.
                os.link(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        else:
            raise FileNotFoundError(f"Graph needs restoration: {asset['path']}")
        checked += 1
    print(f"Verified {checked} graph files against the publication manifest.")


if __name__ == "__main__":
    main()
