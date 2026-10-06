import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from x_workflows_collector.collector import diagnose_empty_timeline, collect_latest_posts, FetchFailure
from x_workflows_collector.cli import main

class DiagnosticsTests(unittest.TestCase):
    def test_rate_limit_and_login_are_distinct(self):
        self.assertEqual(diagnose_empty_timeline('https://x.com/test','',429,True).code,'rate_limited')
        self.assertEqual(diagnose_empty_timeline('https://x.com/i/flow/login','',200,True).code,'authentication_required')
        self.assertEqual(diagnose_empty_timeline('https://x.com/test','',200,False).code,'authentication_required')
        self.assertEqual(diagnose_empty_timeline('https://x.com/test','Verify you are human',200,True).code,'access_restricted')
        self.assertEqual(diagnose_empty_timeline('https://x.com/test','',200,True).code,'timeline_unavailable')

    def test_unexpected_errors_do_not_leak_session_details(self):
        with patch('x_workflows_collector.collector.fetch_latest_post_authenticated',side_effect=RuntimeError('secret cookie')):
            result=collect_latest_posts(['test'],None,100,0,'state.json')
        self.assertEqual(result['errors'][0]['error'],'X collection failed')

    def test_failed_collection_exits_nonzero_but_preserves_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'output.json'
            payload={'posts':[],'errors':[{'handle':'test','error':'X login required'}]}
            with patch('sys.argv',['collector','--output',str(output)]),patch('x_workflows_collector.cli.load_accounts',return_value=['test']),patch('x_workflows_collector.cli.collect_latest_posts',return_value=payload):
                self.assertEqual(main(),1)
            self.assertEqual(json.loads(output.read_text()),payload)
