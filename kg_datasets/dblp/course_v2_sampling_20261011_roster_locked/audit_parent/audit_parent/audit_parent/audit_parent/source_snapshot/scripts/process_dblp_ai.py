"""Build a reproducible Neo4j-ready AI literature sample from DBLP XML."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import re
import shutil
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree


RECORD_TAGS = (
    "article",
    "inproceedings",
    "proceedings",
    "book",
    "incollection",
    "phdthesis",
    "mastersthesis",
    "www",
    "data",
)
TOPIC_PATTERNS = {
    "machine-learning": (
        "Machine Learning",
        r"\bmachine learning\b|\bdeep learning\b|\bneural networks?\b|"
        r"\brepresentation learning\b|\btransfer learning\b|\bfederated learning\b",
    ),
    "large-language-model": (
        "Large Language Model",
        r"\blarge language models?\b|\bllms?\b|\bfoundation models?\b|\btransformers?\b",
    ),
    "natural-language-processing": (
        "Natural Language Processing",
        r"\bnatural language processing\b|\bquestion answering\b|"
        r"\binformation extraction\b|\bnamed entity recognition\b|"
        r"\btext classification\b|\bmachine translation\b",
    ),
    "computer-vision": (
        "Computer Vision",
        r"\bcomputer vision\b|\bobject detection\b|\bimage segmentation\b|"
        r"\bimage recognition\b|\bvisual question answering\b",
    ),
    "knowledge-graph": (
        "Knowledge Graph",
        r"\bknowledge graphs?\b|\bsemantic web\b|\blinked data\b|"
        r"\bontology\b|\bontologies\b|\bentity linking\b|\brelation extraction\b",
    ),
    "reinforcement-learning": (
        "Reinforcement Learning",
        r"\breinforcement learning\b|\bmulti-agent reinforcement learning\b|"
        r"\bintelligent agents?\b",
    ),
    "graph-neural-network": (
        "Graph Neural Network",
        r"\bgraph neural networks?\b|\bgraph convolutional networks?\b|"
        r"\bgraph representation learning\b",
    ),
    "generative-ai": (
        "Generative AI",
        r"\bgenerative ai\b|\bgenerative artificial intelligence\b|"
        r"\bdiffusion models?\b|\btext-to-image\b|\bimage generation\b",
    ),
}
COMPILED_TOPICS = {
    topic_id: (name, re.compile(pattern))
    for topic_id, (name, pattern) in TOPIC_PATTERNS.items()
}
DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+", re.I)


class LocalDTDResolver(etree.Resolver):
    """Allow only the inspected DBLP DTD, never arbitrary local/network files."""

    def __init__(self, dtd: Path):
        super().__init__()
        self.dtd = dtd.resolve()

    def resolve(self, url, public_id, context):
        if url not in {self.dtd.name, str(self.dtd), self.dtd.as_uri(),
                       self.dtd.as_uri().replace("file:///", "file:/")}:
            raise ValueError(f"External XML resource forbidden: {url}")
        return self.resolve_filename(str(self.dtd), context)


def inspect_dtd(source: Path) -> Path:
    with gzip.open(source, "rb") as stream:
        header = stream.read(65536)
    header = re.sub(rb"<!--.*?-->", b"", header, flags=re.S)
    match = re.match(rb'\s*(?:<\?xml\s+[^?]*\?>\s*)?<!DOCTYPE\s+dblp\s+SYSTEM\s+"(dblp(?:-\d{4}-\d{2}-\d{2})?\.dtd)"\s*>\s*<dblp(?:\s|>)', header)
    # A strict header also rejects internal subsets (including local-file entities).
    if not match or header.count(b"<!DOCTYPE") != 1:
        raise ValueError("Expected DBLP SYSTEM DOCTYPE without an internal subset")
    dtd = source.parent / match.group(1).decode("ascii")
    if not dtd.is_file() or dtd.is_symlink():
        raise ValueError(f"Missing/non-local DTD: {dtd}")
    contents = re.sub(rb"<!--.*?-->", b"", dtd.read_bytes(), flags=re.S)
    if re.search(rb'<!ENTITY\s+(?:%\s+)?[^\s]+\s+(?:SYSTEM|PUBLIC)\b', contents):
        raise ValueError("External entities in the DTD are forbidden")
    return dtd


@dataclass(frozen=True, slots=True)
class Publication:
    publication_id: str
    title: str
    publication_type: str
    year: int
    pages: str
    doi: str
    urls: tuple[str, ...]
    authors: tuple[str, ...]
    venue: str
    venue_type: str
    topics: tuple[tuple[str, str], ...]


def clean_text(value: str | None) -> str:
    """Normalize display text without changing its semantic content."""
    return " ".join(unicodedata.normalize("NFKC", value or "").split())


def stable_id(prefix: str, value: str) -> str:
    normalized = clean_text(value).casefold()
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def classify_title(title: str) -> tuple[tuple[str, str], ...]:
    normalized = clean_text(title).casefold()
    matches = []
    for topic_id, (topic_name, pattern) in COMPILED_TOPICS.items():
        match = pattern.search(normalized)
        if match:
            matches.append((topic_id, match.group(0)))
    return tuple(matches)


def element_text(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return clean_text("".join(element.itertext()))


def extract_doi(urls: tuple[str, ...]) -> str:
    for url in urls:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() in {"http", "https"} and parsed.netloc.lower() in {"doi.org", "dx.doi.org"}:
            doi = unquote(parsed.path.lstrip("/"))
            if DOI_PATTERN.fullmatch(doi):
                # DBLP supplies URLs, not prose: trailing punctuation may be legal.
                return doi.casefold()
    return ""


def parse_publication(
    element: etree._Element, start_year: int, end_year: int
) -> tuple[Publication | None, str]:
    publication_id = element.get("key", "").strip()
    title = element_text(element.find("title"))
    year_text = element_text(element.find("year"))
    if not publication_id or not title:
        return None, "missing_required_field"
    try:
        year = int(year_text)
    except ValueError:
        return None, "invalid_year"
    if not start_year <= year <= end_year:
        return None, "year_out_of_range"
    topics = classify_title(title)
    if not topics:
        return None, "no_ai_topic_match"

    publication_type = element.tag
    venue_tag = "journal" if publication_type == "article" else "booktitle"
    venue_type = "journal" if publication_type == "article" else "conference"
    urls = tuple(
        dict.fromkeys(
            value
            for child in element.findall("ee")
            if (value := element_text(child))
        )
    )
    authors = tuple(
        value
        for child in element.findall("author")
        if (value := element_text(child))
    )
    return (
        Publication(
            publication_id=publication_id,
            title=title,
            publication_type=publication_type,
            year=year,
            pages=element_text(element.find("pages")),
            doi=extract_doi(urls),
            urls=urls,
            authors=authors,
            venue=element_text(element.find(venue_tag)),
            venue_type=venue_type,
            topics=topics,
        ),
        "selected_candidate",
    )


def select_publications(
    source: Path, limit: int, seed: int, start_year: int, end_year: int
) -> tuple[list[Publication], dict[str, object]]:
    rng = random.Random(seed)
    sample: list[Publication] = []
    record_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    candidate_topics: Counter[str] = Counter()
    candidate_years: Counter[int] = Counter()
    candidate_count = 0

    dtd = inspect_dtd(source)
    with gzip.open(source, "rb") as stream:
        context = etree.iterparse(
            stream,
            events=("end",),
            tag=RECORD_TAGS,
            load_dtd=True,
            resolve_entities=True,
            no_network=True,
            huge_tree=True,
        )
        context.resolvers.add(LocalDTDResolver(dtd))
        for _, element in context:
            record_counts[element.tag] += 1
            if element.tag in {"article", "inproceedings"}:
                publication, reason = parse_publication(element, start_year, end_year)
                rejection_counts[reason] += 1
                if publication is not None:
                    candidate_count += 1
                    candidate_years[publication.year] += 1
                    candidate_topics.update(topic_id for topic_id, _ in publication.topics)
                    if len(sample) < limit:
                        sample.append(publication)
                    else:
                        position = rng.randrange(candidate_count)
                        if position < limit:
                            sample[position] = publication
            element.clear()
            parent = element.getparent()
            while parent is not None and element.getprevious() is not None:
                del parent[0]

    sample.sort(key=lambda item: item.publication_id)
    stats: dict[str, object] = {
        "source_record_counts": dict(sorted(record_counts.items())),
        "filter_counts": dict(sorted(rejection_counts.items())),
        "candidate_count": candidate_count,
        "candidate_topics": dict(sorted(candidate_topics.items())),
        "candidate_years": {
            str(year): count for year, count in sorted(candidate_years.items())
        },
    }
    return sample, stats


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def write_outputs(
    output: Path,
    publications: list[Publication],
    stats: dict[str, object],
    source: Path,
    seed: int,
    start_year: int,
    end_year: int,
    *,
    snapshot_date: str | None = None,
) -> dict[str, object]:
    if snapshot_date is not None and date.fromisoformat(snapshot_date).isoformat() != snapshot_date:
        raise ValueError('Snapshot date must be YYYY-MM-DD')
    persons: dict[str, str] = {}
    venues: dict[str, tuple[str, str]] = {}
    topics: dict[str, str] = {}
    authored: list[list[object]] = []
    published_in: list[list[object]] = []
    about: list[list[object]] = []
    missing_authors = 0
    missing_venues = 0

    for publication in publications:
        if not publication.authors:
            missing_authors += 1
        for position, author in enumerate(publication.authors, start=1):
            # ponytail: name-based IDs are sufficient for the course sample;
            # use DBLP homepage alias mapping if publication-grade disambiguation is needed.
            person_id = stable_id("person", author)
            persons.setdefault(person_id, author)
            authored.append([person_id, publication.publication_id, position, "AUTHORED"])
        if publication.venue:
            venue_id = stable_id(
                "venue", f"{publication.venue_type}\0{publication.venue}"
            )
            venues.setdefault(venue_id, (publication.venue, publication.venue_type))
            published_in.append(
                [publication.publication_id, venue_id, "PUBLISHED_IN"]
            )
        else:
            missing_venues += 1
        for topic_id, matched_term in publication.topics:
            topics[topic_id] = COMPILED_TOPICS[topic_id][0]
            about.append(
                [
                    publication.publication_id,
                    topic_id,
                    "title_keyword",
                    matched_term,
                    "v1",
                    "ABOUT",
                ]
            )

    write_csv(
        output / "persons.csv",
        ["personId:ID(Person)", "name", "aliases:string[]", ":LABEL"],
        [[key, value, "", "Person"] for key, value in sorted(persons.items())],
    )
    write_csv(
        output / "publications.csv",
        [
            "publicationId:ID(Publication)",
            "title",
            "type",
            "year:int",
            "pages",
            "doi",
            "urls:string[]",
            ":LABEL",
        ],
        [
            [
                item.publication_id,
                item.title,
                item.publication_type,
                item.year,
                item.pages,
                item.doi,
                ";".join(item.urls),
                "Publication",
            ]
            for item in publications
        ],
    )
    write_csv(
        output / "venues.csv",
        ["venueId:ID(Venue)", "name", "venueType", ":LABEL"],
        [
            [venue_id, name, venue_type, "Venue"]
            for venue_id, (name, venue_type) in sorted(venues.items())
        ],
    )
    write_csv(
        output / "topics.csv",
        ["topicId:ID(Topic)", "name", ":LABEL"],
        [[topic_id, name, "Topic"] for topic_id, name in sorted(topics.items())],
    )
    write_csv(
        output / "authored.csv",
        [":START_ID(Person)", ":END_ID(Publication)", "position:int", ":TYPE"],
        authored,
    )
    write_csv(
        output / "published_in.csv",
        [":START_ID(Publication)", ":END_ID(Venue)", ":TYPE"],
        published_in,
    )
    write_csv(
        output / "about.csv",
        [
            ":START_ID(Publication)",
            ":END_ID(Topic)",
            "method",
            "matchedTerm",
            "ruleVersion",
            ":TYPE",
        ],
        about,
    )

    selected_topics = Counter(
        topic_id for item in publications for topic_id, _ in item.topics
    )
    selected_years = Counter(item.year for item in publications)
    selected_types = Counter(item.publication_type for item in publications)
    summary = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "file": str(source.resolve()),
            "bytes": source.stat().st_size,
            "md5": file_md5(source),
            "snapshot": snapshot_date,
            "snapshot_basis": "user_declared_not_independently_verified" if snapshot_date else "unknown",
        },
        "filter": {
            "record_types": ["article", "inproceedings"],
            "start_year": start_year,
            "end_year": end_year,
            "title_rule_version": "v1",
            "sample_method": "deterministic reservoir sampling",
            "sample_seed": seed,
            "topic_patterns": {
                topic_id: pattern for topic_id, (_, pattern) in TOPIC_PATTERNS.items()
            },
        },
        **stats,
        "selected": {
            "publications": len(publications),
            "persons": len(persons),
            "venues": len(venues),
            "topics": len(topics),
            "authored_relationships": len(authored),
            "published_in_relationships": len(published_in),
            "about_relationships": len(about),
            "publication_types": dict(sorted(selected_types.items())),
            "years": {str(year): count for year, count in sorted(selected_years.items())},
            "topic_assignments": dict(sorted(selected_topics.items())),
            "publications_without_authors": missing_authors,
            "publications_without_venues": missing_venues,
        },
        "known_limitations": [
            "AI topics are inferred from title keyword rules, not supplied by DBLP.",
            "Person IDs are based on normalized author names; DBLP homepage alias mapping is not applied.",
            "CITES, EDITED, PART_OF, and derived coauthor relationships are not included in v1.",
        ],
    }
    (output / "quality_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "processing_report.md").write_text(
        render_processing_report(summary), encoding="utf-8"
    )
    return summary


def render_processing_report(summary: dict[str, object]) -> str:
    selected = summary["selected"]
    source = summary["source"]
    filters = summary["filter"]
    return f"""# DBLP人工智能文献数据处理报告

## 数据来源

- 快照日期：{source['snapshot'] or '未知（未声明）'}；日期仅为显式声明，不是独立核验结论。
- 原始文件：`{source['file']}`
- 文件大小：{source['bytes']:,} 字节
- MD5：`{source['md5']}`

## 处理规则

- 文献类型：`article`、`inproceedings`
- 年份范围：{filters['start_year']}—{filters['end_year']}
- 主题识别：论文标题关键词规则 `{filters['title_rule_version']}`
- 抽样方法：{filters['sample_method']}，固定种子 `{filters['sample_seed']}`
- AI候选论文：{summary['candidate_count']:,} 篇

## 输出规模

| 内容 | 数量 |
|---|---:|
| Publication节点 | {selected['publications']:,} |
| Person节点 | {selected['persons']:,} |
| Venue节点 | {selected['venues']:,} |
| Topic节点 | {selected['topics']:,} |
| AUTHORED关系 | {selected['authored_relationships']:,} |
| PUBLISHED_IN关系 | {selected['published_in_relationships']:,} |
| ABOUT关系 | {selected['about_relationships']:,} |

## 质量说明

- 节点ID唯一性和关系端点完整性须由独立审计脚本复核；本生成报告不代替校验。
- 论文类型和年份均符合筛选范围。
- 有{selected['publications_without_authors']:,}篇论文没有作者字段，有{selected['publications_without_venues']:,}篇没有场馆字段；论文仍保留，缺失关系不创建。
- 主题是由标题规则推断，不是DBLP原始主题标签。
- 第一版作者ID基于规范化姓名，尚未进行DBLP人物主页级别的别名消歧。
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("kg_datasets/dblp/dblp.xml.gz"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("kg_datasets/dblp/processed_ai")
    )
    parser.add_argument("--limit", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--snapshot-date", help="Declared source date YYYY-MM-DD; omitted means unknown, not independently verified")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.start_year > args.end_year:
        parser.error("--start-year cannot exceed --end-year")
    if args.snapshot_date is not None:
        try:
            if date.fromisoformat(args.snapshot_date).isoformat() != args.snapshot_date:
                raise ValueError('Noncanonical ISO date')
        except ValueError:
            parser.error("--snapshot-date must be a valid YYYY-MM-DD date")
    return args


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"DBLP source not found: {source}")
    if output.exists() and not args.force:
        raise FileExistsError(f"Output already exists; pass --force to replace: {output}")

    validate_output_target(source, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent)).resolve()
    try:
        publications, stats = select_publications(
            source,
            args.limit,
            args.seed,
            args.start_year,
            args.end_year,
        )
        summary = write_outputs(
            temporary,
            publications,
            stats,
            source,
            args.seed,
            args.start_year,
            args.end_year,
            snapshot_date=args.snapshot_date,
        )
        if len(publications) < args.limit:
            raise RuntimeError(
                f"Only {len(publications)} matching publications found; requested {args.limit}"
            )
        if output.exists():
            backup = output.with_name(output.name + ".backup-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
            output.rename(backup)
            print(f"Previous output preserved: {backup}")
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    selected = summary["selected"]
    print(json.dumps(selected, ensure_ascii=False, indent=2))


def validate_output_target(source: Path, output: Path) -> None:
    if output == Path(output.anchor) or output == Path.cwd().resolve() or source.is_relative_to(output):
        raise ValueError("Output must not be a root/workspace directory or contain the source")
    if output.exists():
        expected = {"persons.csv", "publications.csv", "venues.csv", "topics.csv", "authored.csv",
                    "published_in.csv", "about.csv", "quality_summary.json", "processing_report.md"}
        if not output.is_dir() or not (output / "quality_summary.json").is_file() or {p.name for p in output.iterdir()} - expected:
            raise ValueError("Refusing to replace a directory that is not a managed DBLP output")


if __name__ == "__main__":
    main()
