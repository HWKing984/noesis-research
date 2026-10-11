# 2026-10-11 GitHub publication

This branch publishes the local `D:\a-open_source\neo4j` AI-Literature-KG project snapshot. Its parent is the existing NOESIS Research `main` commit; the branch tree represents this local project rather than merging the separate application's source files. The remote `main` branch is unchanged by this publication.

Source scripts, tests, schemas, resources, annotations, dependency files, documentation, experimental inputs, metrics, review receipts, evidence and delivery archives are included. Local Python environments, caches, personal tooling and pytest scratch directories are excluded.

Model weights and original DBLP/IMDb corpus downloads are excluded from ordinary Git storage. `large_assets.json` records their original relative paths, byte sizes and SHA-256 checksums. Model configs, tokenizers, training scripts, evaluation outputs and provenance remain included; this snapshot alone does not provide the omitted model weights or original corpora. Use the project's documented preparation/training procedures or copy matching assets from the original local project. No model is retrained or promoted during publication.

Graph JSONL files exceeding the publication's 95 MiB per-file threshold are included as byte-preserving `.jsonl.gz` companions. After cloning, restore them before running graph import or file-integrity verification:

```powershell
python scripts/restore_publication_graphs.py
python scripts/restore_publication_graphs.py --verify-only
```

Restoration checks every restored file's byte size and SHA-256, and refuses to overwrite a differing existing file. The complete project usage and model/evidence limitations remain documented in the root README.
