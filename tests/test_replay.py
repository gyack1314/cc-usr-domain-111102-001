import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from workbench import alignment
from workbench.domain import validate_net
from workbench.io import read_json, write_json
from workbench.replay import replay

ROOT = Path(__file__).resolve().parents[1]


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.net = validate_net(read_json(ROOT / 'samples/nets.json')[0])
        self.costs = read_json(ROOT / 'samples/costs.json')[0]
        rows = read_json(ROOT / 'samples/events.json')
        self.cases = {}
        for row in rows:
            self.cases.setdefault(row['case_id'], []).append(row)
        for group in self.cases.values():
            group.sort(key=lambda r: r['sequence'])
        self.result = alignment.align(self.net, self.cases['A'], self.costs, 'A', 'port')

    def _verdict(self, explanation=None):
        explanation = self.result if explanation is None else explanation
        return replay(self.net, self.cases['A'], self.costs, explanation, 'A', 'port')

    def test_valid_explanation_passes(self):
        verdict = self._verdict()
        self.assertTrue(verdict['valid'])
        self.assertEqual(verdict['cost'], 0)
        self.assertEqual(verdict['events_consumed'], ['e1', 'e2', 'e3'])
        self.assertEqual(verdict['final_marking'], ['end'])

    def test_replay_rejects_tampered_firing(self):
        bad = deepcopy(self.result)
        bad['moves'][1]['tokens_after'] = ['end']  # 与真实发火不符
        verdict = self._verdict(bad)
        self.assertFalse(verdict['valid'])
        self.assertEqual(verdict['reason'], '动作后令牌与复演不一致')

    def test_replay_rejects_double_consumption(self):
        bad = deepcopy(self.result)
        bad['moves'][2]['event_id'] = 'e1'  # e1被第二次引用
        verdict = self._verdict(bad)
        self.assertFalse(verdict['valid'])
        self.assertIn('事件', verdict['reason'])

    def test_replay_rejects_missing_event(self):
        bad = deepcopy(self.result)
        del bad['moves'][2]['event_id']
        bad['moves'][2]['event_id'] = ''
        bad['moves'][2]['type'] = 'model'
        verdict = self._verdict(bad)
        self.assertFalse(verdict['valid'])

    def test_replay_rejects_wrong_final_marking(self):
        bad = deepcopy(self.result)
        bad['final_marking'] = ['start']
        verdict = self._verdict(bad)
        self.assertFalse(verdict['valid'])

    def test_replay_rejects_cost_mismatch(self):
        bad = deepcopy(self.result)
        bad['moves'][0]['cost'] = 9
        verdict = self._verdict(bad)
        self.assertEqual(verdict['reason'], '动作偏差代价与配置不符')

    def test_replay_rejects_silent_sync(self):
        bad = deepcopy(self.result)
        bad['moves'][0]['type'] = 'sync'
        bad['moves'][0]['event_id'] = 'e1'
        verdict = self._verdict(bad)
        self.assertEqual(verdict['reason'], '静默转换不能做同步动作')

    def test_replay_rejects_unknown_transition(self):
        bad = deepcopy(self.result)
        bad['moves'][0]['transition_id'] = 'ghost'
        verdict = self._verdict(bad)
        self.assertEqual(verdict['reason'], '动作引用不存在的转换')


class FailureStatusTests(unittest.TestCase):
    def setUp(self):
        self.costs = read_json(ROOT / 'samples/costs.json')[0]

    def test_unreachable_terminal_status(self):
        net = validate_net({
            'id': 'dead', 'places': ['p0', 'p1'], 'initial': ['p0'], 'final': ['p1'],
            'transitions': [{'id': 'a', 'label': 'A', 'pre': ['p0'], 'post': ['p0']}]})
        result = alignment.align(net, [{'event_id': 'x', 'case_id': 'X',
                                        'sequence': 1, 'activity': 'A'}], self.costs, 'X', 'dead')
        self.assertEqual(result['status'], alignment.UNREACHABLE)
        # 状态空间已完整穷尽，只是终态不可达；无提前结束
        self.assertTrue(result['complete'])
        self.assertIsNone(result['cost'])

    def test_invalid_net_is_distinct_status(self):
        net = {'id': 'bad', 'places': ['p0', 'p0'], 'initial': ['p0'], 'final': [],
               'transitions': []}
        result = alignment.safe_align(net, [], self.costs, 'X', 'bad')
        self.assertEqual(result['status'], alignment.INVALID_NET)
        self.assertTrue(result['error'])

    def test_resource_exhausted_is_distinct_and_not_claimed_optimal(self):
        net = validate_net(read_json(ROOT / 'samples/nets.json')[0])
        rows = [r for r in read_json(ROOT / 'samples/events.json') if r['case_id'] == 'A']
        # 首状态就有多个后继，限额1必然在找到终态前耗尽
        tight = dict(self.costs, search_limit=1)
        result = alignment.align(net, rows, tight, 'A', 'port')
        self.assertEqual(result['status'], alignment.RESOURCE_EXHAUSTED)
        self.assertFalse(result['complete'])
        self.assertIsNone(result['cost'])
        self.assertGreaterEqual(result['expanded'], 1)

    def test_duplicate_event_id_rejected(self):
        with self.assertRaises(ValueError):
            alignment.validate_events([
                {'event_id': 'e', 'case_id': 'A', 'sequence': 1, 'activity': 'A'},
                {'event_id': 'e', 'case_id': 'B', 'sequence': 1, 'activity': 'A'}])

    def test_bad_costs_is_not_reported_as_invalid_net(self):
        good_net = validate_net(read_json(ROOT / 'samples/nets.json')[0])
        with self.assertRaises(ValueError):
            alignment.safe_align(good_net, [], {'log': -1, 'model': 3})
        with self.assertRaises(ValueError):
            alignment.align_all([good_net], [], {'log': 1, 'model': 1, 'search_limit': 0})
        # 非法网仍独立成结果，不与配置错误混淆
        bad_net = {'id': 'bad', 'places': ['p', 'p'], 'initial': [], 'final': [], 'transitions': []}
        result = alignment.safe_align(bad_net, [], {'log': 1, 'model': 1})
        self.assertEqual(result['status'], alignment.INVALID_NET)


class CliBatchTests(unittest.TestCase):
    def test_align_and_verify_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'result.json'
            cmd = [sys.executable, '-m', 'workbench.cli', 'align',
                   str(ROOT / 'samples/nets.json'), str(ROOT / 'samples/events.json'),
                   str(ROOT / 'samples/costs.json'), '--output', str(out)]
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual([r['case_id'] for r in payload['results']], ['A', 'B', 'C'])
            self.assertTrue(all(r['status'] == 'optimal' for r in payload['results']))
            cmd = [sys.executable, '-m', 'workbench.cli', 'verify',
                   str(ROOT / 'samples/nets.json'), str(ROOT / 'samples/events.json'),
                   str(ROOT / 'samples/costs.json'), str(out)]
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(json.loads(run.stdout)['all_valid'])

    def test_verify_detects_tampered_payload(self):
        net = validate_net(read_json(ROOT / 'samples/nets.json')[0])
        costs = read_json(ROOT / 'samples/costs.json')[0]
        rows = [r for r in read_json(ROOT / 'samples/events.json') if r['case_id'] == 'A']
        result = alignment.align(net, rows, costs, 'A', 'port')
        result['moves'][0]['tokens_after'] = ['nope']
        with tempfile.TemporaryDirectory() as d:
            nets_path, events_path, costs_path = Path(d) / 'nets.json', Path(d) / 'events.json', Path(d) / 'costs.json'
            write_json(nets_path, [net]); write_json(events_path, rows); write_json(costs_path, [costs])
            explanation_path = Path(d) / 'ex.json'
            write_json(explanation_path, result)
            cmd = [sys.executable, '-m', 'workbench.cli', 'verify',
                   str(nets_path), str(events_path), str(costs_path), str(explanation_path)]
            run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 3)
            self.assertFalse(json.loads(run.stdout)['all_valid'])

    def test_cli_missing_file_returns_code_2(self):
        cmd = [sys.executable, '-m', 'workbench.cli', 'align',
               'no-such-nets.json', str(ROOT / 'samples/events.json'),
               str(ROOT / 'samples/costs.json'), '--output', 'unused.json']
        run = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('资料读取失败', run.stderr)


if __name__ == '__main__':
    unittest.main()
