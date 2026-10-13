import tempfile
import contextlib
import io
import unittest
from pathlib import Path
from hallu_cite_checker.audit import audit
from hallu_cite_checker.cli import main
from hallu_cite_checker.evidence import add_evidence, trusted
from hallu_cite_checker.inventory import inventory_latex, parse_bib
from hallu_cite_checker.io import load, save

BIB = """@inproceedings{ref,
 title={Reliable {Multimodal} Learning},
 author={Alice Smith and Bob Jones},
 year={2024},
 booktitle={International Conference on Learning Representations},
 pages={10--20}
}
"""


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "paper"
        self.project.mkdir()
        (self.project / "main.bib").write_text(BIB)
        (self.project / "main.tex").write_text(r"\cite{ref}")
        self.run = self.root / "run"
        inventory_latex(self.project, self.run)
        self.original = load(self.run / "manifest.json")

    def tearDown(self):
        self.temp.cleanup()

    def confirm(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return main(["confirm-coverage", str(self.run), "--reviewer", "test", "--note", "All source entries reconciled"])

    def evidence(self, bib=BIB, **kwargs):
        path = self.root / ("evidence-" + str(len(load(self.run / "evidence.json")["records"])) + ".bib")
        path.write_text(bib)
        return add_evidence(self.run, "ref", path, "google_scholar", "https://scholar.google.com/scholar.bib?output=citation",
                            "bibtex", version_id="iclr:2024:ref", **kwargs)

    def mutate(self, **fields):
        manifest = load(self.run / "manifest.json")
        manifest["references"][0]["fields"].update(fields)
        save(self.run / "manifest.json", manifest)

    def result(self):
        return audit(self.run)

    def test_valid_export_passes(self):
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["verdict"], "PASS")

    def test_no_evidence_never_passes(self):
        self.confirm()
        self.assertEqual(self.result()["counts"]["UNVERIFIED"], 1)

    def test_missing_coverage_never_passes(self):
        self.evidence()
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_tampered_year_rejected(self):
        self.mutate(year="2025")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_wrong_venue_rejected(self):
        self.mutate(venue="CVPR")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_title_and_authors_rejected(self):
        for fields in ({"title": "Invented Multimodal Learning"}, {"authors": ["Alice Smith", "Fake Author"]}):
            with self.subTest(fields=fields):
                save(self.run / "manifest.json", self.original)
                save(self.run / "evidence.json", {"records": [], "attempts": []})
                self.mutate(**fields)
                self.evidence()
                self.confirm()
                self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_missing_pages_in_source_allowed_but_disclosed(self):
        self.evidence(BIB.replace(" pages={10--20}\n", ""))
        self.confirm()
        report = self.result()
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["references"][0]["unchecked_optional_fields"], ["pages"])

    def test_missing_input_pages_allowed(self):
        manifest = load(self.run / "manifest.json")
        del manifest["references"][0]["fields"]["pages"]
        save(self.run / "manifest.json", manifest)
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["verdict"], "PASS")

    def test_wrong_pages_rejected(self):
        self.mutate(pages="11-20")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_preprint_does_not_prove_conference(self):
        self.evidence(BIB.replace("International Conference on Learning Representations", "arXiv"))
        self.confirm()
        self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_missing_claimed_venue_blocks(self):
        self.evidence(BIB.replace(" booktitle={International Conference on Learning Representations},\n", ""))
        self.confirm()
        self.assertEqual(self.result()["counts"]["UNVERIFIED"], 1)

    def test_wrong_or_unverified_doi_blocks(self):
        self.mutate(doi="10.1234/fake")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_unknown_bibliographic_field_blocks(self):
        self.mutate(note="Main conference accepted")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["counts"]["UNVERIFIED"], 1)

    def test_evidence_file_tamper_blocks(self):
        record = self.evidence()
        self.confirm()
        (self.run / record["artifact"]).write_text(BIB.replace("2024", "2025"))
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_evidence_metadata_tamper_blocks(self):
        self.evidence()
        self.confirm()
        data = load(self.run / "evidence.json")
        data["records"][0]["fields"]["year"] = "2025"
        save(self.run / "evidence.json", data)
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_input_file_changes_block(self):
        self.evidence()
        self.confirm()
        (self.project / "main.bib").write_text(BIB + "\n")
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_inventory_changes_invalidate_coverage(self):
        self.evidence()
        self.confirm()
        self.mutate(title="Other paper")
        self.assertTrue(any(b["code"] == "coverage_not_confirmed" for b in self.result()["blockers"]))

    def test_known_conflicting_source_cannot_be_ignored(self):
        self.evidence()
        self.evidence(BIB.replace("2024", "2025"))
        self.confirm()
        self.assertEqual(self.result()["counts"]["UNVERIFIED"], 1)
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_author_initials_and_venue_alias(self):
        self.mutate(authors=["A. Smith", "B. Jones"], venue="ICLR", pages="10–20")
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["verdict"], "PASS")

    def test_missing_author_or_wrong_author_order_rejected(self):
        self.mutate(authors=["Bob Jones", "Alice Smith"])
        self.evidence()
        self.confirm()
        self.assertEqual(self.result()["counts"]["REJECTED"], 1)

    def test_duplicate_keys_block(self):
        (self.project / "appendix.bib").write_text(BIB)
        run = self.root / "duplicate-run"
        manifest = inventory_latex(self.project, run)
        self.assertTrue(any(b["code"] == "duplicate_citation_keys" for b in manifest["issues"]))

    def test_all_nested_and_unused_entries_included(self):
        (self.project / "sec").mkdir()
        (self.project / "sec" / "extra.bib").write_text(BIB.replace("{ref,", "{unused,"))
        manifest = inventory_latex(self.project, self.root / "nested-run")
        self.assertEqual({r["id"] for r in manifest["references"]}, {"ref", "unused"})

    def test_empty_inventory_never_passes(self):
        manifest = load(self.run / "manifest.json")
        manifest["references"] = []
        save(self.run / "manifest.json", manifest)
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_source_host_spoof_rejected(self):
        self.assertFalse(trusted("google_scholar", "https://scholar.google.com.evil.org/scholar.bib"))
        self.assertFalse(trusted("official", "https://evil.org"))
        self.assertFalse(trusted("google_scholar", "https://evil@scholar.google.com/"))

    def test_malformed_bib_does_not_silently_drop_entry(self):
        with self.assertRaises(Exception):
            parse_bib(BIB + "@article{broken, title={oops", "broken.bib")

    def test_correct_arxiv_citation_passes(self):
        self.mutate(venue="arXiv", arxiv_id="2401.01234")
        evidence = BIB.replace("International Conference on Learning Representations", "arXiv").replace(" pages", " eprint={2401.01234},\n pages")
        self.evidence(evidence)
        self.confirm()
        self.assertEqual(self.result()["verdict"], "PASS")

    def test_linked_version_supports_identifier_without_mixing_venue(self):
        self.mutate(arxiv_id="2401.01234")
        self.evidence()
        self.evidence(BIB.replace("International Conference on Learning Representations", "arXiv").replace(" pages", " eprint={2401.01234},\n pages"),
                      role="linked_version", reviewer="test", relation="Official primary record links this preprint")
        self.confirm()
        self.assertEqual(self.result()["verdict"], "PASS")

    def test_fake_linked_paper_cannot_validate_identifier(self):
        self.mutate(arxiv_id="2401.01234")
        self.evidence()
        self.evidence(BIB.replace("Reliable {Multimodal} Learning", "Unrelated Paper").replace(" pages", " eprint={2401.01234},\n pages"),
                      role="linked_version", reviewer="test", relation="alleged link")
        self.confirm()
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_wrong_linked_authors_block(self):
        self.mutate(arxiv_id="2401.01234")
        self.evidence()
        self.evidence(BIB.replace("Alice Smith and Bob Jones", "Different Person").replace(" pages", " eprint={2401.01234},\n pages"),
                      role="linked_version", reviewer="test", relation="alleged link")
        self.confirm()
        self.assertEqual(self.result()["verdict"], "FAIL")

    def test_pdf_extraction_never_auto_confirms_coverage(self):
        from pypdf import PdfWriter
        from hallu_cite_checker.inventory import inventory_pdf
        pdf = self.root / "empty.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=600, height=800)
        with pdf.open("wb") as file:
            writer.write(file)
        manifest = inventory_pdf(pdf, self.root / "pdf-run")
        self.assertFalse(manifest["coverage"]["reviewed"])
        self.assertTrue(manifest["issues"])
        self.assertEqual(audit(self.root / "pdf-run")["verdict"], "FAIL")

    def test_reviewed_metadata_requires_saved_source(self):
        file = self.root / "meta.json"
        save(file, {"fields": {"title": "X"}, "reviewer": "test", "field_provenance": {"title": "heading"}})
        with self.assertRaises(ValueError):
            add_evidence(self.run, "ref", file, "official", "https://openreview.net/forum?id=x", "reviewed_metadata", version_id="x")

    def test_report_html_escapes_input(self):
        self.mutate(title='<script>alert("X")</script>')
        self.evidence()
        self.confirm()
        self.result()
        page = (self.run / "report.html").read_text()
        self.assertNotIn('<script>alert("X")</script>', page)


if __name__ == "__main__":
    unittest.main()
