import sys
import gzip
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from process_dblp_ai import classify_title, clean_text, extract_doi, stable_id, select_publications, inspect_dtd, validate_output_target, write_outputs, main


class ProcessingRulesTest(unittest.TestCase):
    def test_snapshot_date_is_explicit_and_not_invented(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'unrelated.xml.gz'
            source.write_bytes(b'synthetic input, not a DBLP snapshot')
            summary = write_outputs(directory, [], {'candidate_count': 0}, source, 42, 2015, 2025)
            self.assertIsNone(summary['source']['snapshot'])
            declared = write_outputs(directory, [], {'candidate_count': 0}, source, 42, 2015, 2025,
                                     snapshot_date='2026-09-01')
            self.assertEqual(declared['source']['snapshot'], '2026-09-01')
            self.assertEqual(declared['source']['snapshot_basis'], 'user_declared_not_independently_verified')
            with self.assertRaises(ValueError):
                write_outputs(directory, [], {'candidate_count': 0}, source, 42, 2015, 2025,
                              snapshot_date='2026-02-30')
            with gzip.open(source, 'wb') as stream:
                stream.write(b'<!DOCTYPE dblp SYSTEM "dblp.dtd"><dblp><article key="test/1"><title>Machine Learning</title><year>2020</year></article></dblp>')
            (directory / 'dblp.dtd').write_text('<!ELEMENT dblp ANY>', encoding='utf-8')
            with patch.object(sys, 'argv', ['process', '--source', str(source), '--output', str(directory / 'cli'),
                                           '--limit', '1', '--snapshot-date', '2026-09-01']), patch('builtins.print'):
                main()
            self.assertIn('2026-09-01', (directory / 'cli' / 'processing_report.md').read_text(encoding='utf-8'))

    def test_core_cleaning_and_classification(self) -> None:
        self.assertEqual(clean_text("  Graph   Neural\nNetwork "), "Graph Neural Network")
        self.assertEqual(stable_id("person", "Zhang San"), stable_id("person", " zhang  san "))
        topics = {topic_id for topic_id, _ in classify_title("Graph Neural Networks for Knowledge Graphs")}
        self.assertEqual(
            topics,
            {"machine-learning", "graph-neural-network", "knowledge-graph"},
        )
        self.assertEqual(
            extract_doi(("https://doi.org/10.1000/Example.",)),
            "10.1000/example.",
        )

    def test_doi_url_preserves_suffix_and_ignores_query(self):
        self.assertEqual(extract_doi(("https://dx.doi.org/10.1000/A%28B%29;?x=1",)), "10.1000/a(b);")
        self.assertEqual(extract_doi(("https://evil.org/https://doi.org/10.1000/a",)), "")

    def test_local_dtd_streaming_and_security(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "mini.xml.gz"
            dtd = directory / "dblp.dtd"
            dtd.write_text('<!ENTITY eacute "é">', encoding="utf-8")
            def save_xml(doctype, title):
                with gzip.open(source, "wb") as stream:
                    stream.write((f'<?xml version="1.0" encoding="UTF-8"?>{doctype}<dblp>'
                                  f'<article key="test/1"><title>Machine Learning &{title};</title><year>2020</year></article></dblp>').encode())
            save_xml('<!DOCTYPE dblp SYSTEM "dblp.dtd">', 'eacute')
            sample, stats = select_publications(source, 1, 42, 2015, 2025)
            self.assertEqual(sample[0].title, "Machine Learning é")
            self.assertEqual(stats["candidate_count"], 1)
            save_xml('<!DOCTYPE dblp SYSTEM "dblp.dtd" [<!ENTITY leak SYSTEM "file:///secret">]>', 'leak')
            with self.assertRaises(ValueError):
                inspect_dtd(source)
            save_xml('<!DOCTYPE dblp SYSTEM "dblp.dtd">', 'eacute')
            dtd.write_text('<!ENTITY eacute SYSTEM "file:///secret">', encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_dtd(source)

    def test_output_target_rejects_source_ancestor_and_unmanaged_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            with self.assertRaises(ValueError):
                validate_output_target(directory / "raw.gz", directory)
            arbitrary = directory / "userfiles"
            arbitrary.mkdir()
            with self.assertRaises(ValueError):
                validate_output_target(directory / "raw.gz", arbitrary)


if __name__ == "__main__":
    unittest.main()
