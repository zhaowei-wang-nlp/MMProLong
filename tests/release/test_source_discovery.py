"""Source outages must not be recorded as successful empty search results."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests


sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
from local_corpus import Corpus, parse_arxiv_raw


class SourceDiscoveryTests(unittest.TestCase):
    def test_bulk_metadata_filters_license_and_keeps_latest_version(self):
        records = []
        for aid, license_url, pages in [
            ("2601.00001", "http://creativecommons.org/licenses/by/4.0/", 20),
            ("2601.00002", "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", 20),
            ("2601.00003", "http://creativecommons.org/licenses/by/4.0/", 5),
        ]:
            records.append(f"""<record><header><datestamp>2026-01-02</datestamp></header><metadata>
            <arXivRaw xmlns="http://arxiv.org/OAI/arXivRaw/"><id>{aid}</id><title>Test</title>
            <authors>A and B</authors><categories>q-bio.NC</categories><license>{license_url}</license>
            <comments>{pages} pages</comments><version version="v1"/><version version="v2"/></arXivRaw>
            </metadata></record>""")
        response = requests.Response()
        response.status_code = 200
        response._content = (
            '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>'
            + "".join(records)
            + "<resumptionToken>next-page</resumptionToken></ListRecords></OAI-PMH>"
        ).encode()
        parsed, token, errors = parse_arxiv_raw(response.content)
        self.assertEqual(parsed[0]["id"], "2601.00001v2")
        self.assertEqual(token, "next-page")
        self.assertEqual(errors, [])
        with tempfile.TemporaryDirectory() as tmp, patch("local_corpus.check_disk"):
            c = self.corpus(response)
            c.root = Path(tmp)
            self.assertEqual(c.discover_bulk(), 1)
            self.assertEqual(c.state["queue"][0]["arxiv_id"], "2601.00001")
            self.assertEqual(c.state["queue"][0]["source_domain"], "Biology")
            self.assertTrue((c.root / c.state["queue"][0]["catalog_record"]).is_file())

    def corpus(self, response):
        c = Corpus.__new__(Corpus)
        c.state = {"query_index": 0, "offsets": {}, "seen": [], "queue": []}
        c.policy = {"min_document_pages": 14, "max_document_pages": 50}
        c.events = []
        c.status = lambda phase, **kw: c.events.append((phase, kw))
        c.public_get = lambda *args, **kwargs: response
        return c

    @patch("local_corpus.time.sleep")
    def test_http_failure_does_not_advance_cursor_or_report_zero_results(self, _):
        response = requests.Response()
        response.status_code = 503
        c = self.corpus(response)
        self.assertIsNone(c.discover())
        self.assertEqual(c.state["offsets"], {})
        self.assertEqual(c.events[-1][1]["http_status"], 503)

    @patch("local_corpus.time.sleep")
    def test_successful_empty_atom_page_is_distinct_from_failure(self, _):
        response = requests.Response()
        response.status_code = 200
        response._content = b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        c = self.corpus(response)
        self.assertEqual(c.discover(), 0)
        self.assertEqual(c.state["offsets"]["review cosmology"], 25)


if __name__ == "__main__":
    unittest.main()
