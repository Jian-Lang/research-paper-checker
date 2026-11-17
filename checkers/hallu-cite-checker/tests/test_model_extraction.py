"""Regression checks for the model extraction handoff and verification boundary."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hallu_cite_checker.automatic import check_pdf, verify_pdf
from hallu_cite_checker.io import save, fingerprint


class ModelExtractionTest(unittest.TestCase):
    def test_current_pdf_does_not_require_fixed_grammar(self):
        pdf = next(Path(__file__).resolve().parents[3].glob('*.pdf'), None)
        if pdf is None:
            self.skipTest('Local PDF fixture unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('hallu_cite_checker.automatic.populate', side_effect=AssertionError('Fixed parser must not run')):
                check_pdf(pdf, tmp)
            manifest = json.loads((Path(tmp) / 'manifest.json').read_text())
            self.assertEqual(len(manifest['pages']), 13)
            self.assertEqual(manifest['execution']['mode'], 'awaiting_model_extraction')
            self.assertFalse(manifest['coverage']['reviewed'])
            self.assertFalse(manifest['execution']['fresh_network_verification'])
            self.assertFalse(any(i['code'] == 'automatic_bibliography_parse' for i in manifest['issues']))
            with self.assertRaisesRegex(ValueError, 'host-model extraction'):
                verify_pdf(tmp)

    def test_empty_or_stale_inventory_cannot_query_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs = [{'id':'1', 'fields':{'title':'Example'}, 'raw':'Example', 'locations':[{'page':1}]}]
            for inventory, coverage in [([], {'reviewed':True}),
                (refs, {'reviewed':False}),
                (refs, {'reviewed':True, 'reference_count':1, 'reference_fingerprint':'stale'})]:
                save(Path(tmp)/'manifest.json', {'mode':'pdf', 'references':inventory, 'issues':[], 'coverage':coverage})
                with patch('hallu_cite_checker.automatic.capture', side_effect=AssertionError('Network must not start')):
                    with self.assertRaises(ValueError):
                        verify_pdf(tmp)

    def test_reviewed_arbitrary_layout_reaches_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            refs = [{'id':'web', 'fields':{'title':'Corporate web citation'}, 'raw':'arbitrary layout', 'locations':[{'page':1}]}]
            save(Path(tmp)/'manifest.json', {'mode':'pdf', 'references':refs, 'issues':[],
                'coverage':{'reviewed':True, 'reference_count':1, 'reference_fingerprint':fingerprint(refs)}})
            # Stop exactly at the network boundary; no metadata service required.
            with patch('hallu_cite_checker.automatic.audit'), patch('hallu_cite_checker.automatic.settings', side_effect=RuntimeError('network boundary')):
                with self.assertRaisesRegex(RuntimeError, 'network boundary'):
                    verify_pdf(tmp)
            manifest = json.loads((Path(tmp)/'manifest.json').read_text())
            self.assertEqual(manifest['execution']['mode'], 'model_extracted_network_check')


if __name__ == '__main__':
    unittest.main()
