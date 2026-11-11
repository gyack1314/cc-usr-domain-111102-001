import unittest
from pathlib import Path

from workbench import alignment
from workbench.domain import validate_net
from workbench.io import read_json

ROOT = Path(__file__).resolve().parents[1]


class PortAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.net = validate_net(read_json(ROOT / 'samples/nets.json')[0])
        self.costs = read_json(ROOT / 'samples/costs.json')[0]
        rows = read_json(ROOT / 'samples/events.json')
        self.cases = {}
        for row in rows:
            self.cases.setdefault(row['case_id'], []).append(row)
        for group in self.cases.values():
            group.sort(key=lambda r: r['sequence'])

    def test_parallel_reorder_is_zero_cost(self):
        result = alignment.align(self.net, self.cases['A'], self.costs, 'A', 'port')
        self.assertEqual(result['status'], alignment.OPTIMAL)
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['events_consumed'], ['e1', 'e2', 'e3'])
        self.assertEqual(result['final_marking'], ['end'])
        kinds = [m['type'] for m in result['moves']]
        self.assertEqual(kinds, ['model', 'sync', 'sync', 'model', 'sync'])
        self.assertEqual([m['transition_id'] for m in result['moves']],
                         ['split', 'check_yard', 'check_docs', 'join', 'permit'])

    def test_missing_release_is_a_model_deviation(self):
        result = alignment.align(self.net, self.cases['B'], self.costs, 'B', 'port')
        self.assertEqual(result['status'], alignment.OPTIMAL)
        self.assertEqual(result['cost'], self.costs['model'])
        tail = result['moves'][-1]
        self.assertEqual((tail['type'], tail['transition_id'], tail['event_id']),
                         ('model', 'permit', ''))
        self.assertEqual(result['events_consumed'], ['e4', 'e5'])

    def test_repeated_scan_matches_rework_loop(self):
        result = alignment.align(self.net, self.cases['C'], self.costs, 'C', 'port')
        self.assertEqual(result['status'], alignment.OPTIMAL)
        self.assertEqual(result['cost'], self.costs['log'] + self.costs['model'])
        log_moves = [m for m in result['moves'] if m['type'] == 'log']
        self.assertEqual([m['event_id'] for m in log_moves], ['e6'])
        model_moves = [(m['transition_id'], m['cost']) for m in result['moves'] if m['type'] == 'model']
        # 可见转换的model动作必须按配置计model代价；permit可由等价路径替代，不要求出现
        self.assertTrue(any(cost == self.costs['model'] for _, cost in model_moves))
        self.assertTrue(all(tid in ('split', 'join') or cost == self.costs['model']
                            for tid, cost in model_moves))
        # 无返工同步路径时rework不应出现在最优解释里
        self.assertNotIn('rework', [m['transition_id'] for m in result['moves']])

    def test_rework_trace_replays_for_free(self):
        rows = read_json(ROOT / 'examples/events_rework.json')
        result = alignment.align(self.net, rows, self.costs, 'D', 'port')
        self.assertEqual(result['status'], alignment.OPTIMAL)
        self.assertEqual(result['cost'], 0)
        ids = [m['transition_id'] for m in result['moves'] if m['type'] != 'log']
        self.assertEqual(ids.count('rework'), 1)
        self.assertEqual(ids.count('check_docs'), 2)
        self.assertEqual(ids.count('check_yard'), 2)

    def test_zero_cost_silent_loop_terminates(self):
        net = validate_net({
            'id': 'loop', 'places': ['p0', 'p1'], 'initial': ['p0'], 'final': ['p1'],
            'transitions': [
                {'id': 'spin', 'label': None, 'pre': ['p0'], 'post': ['p0']},
                {'id': 'go', 'label': 'G', 'pre': ['p0'], 'post': ['p1']}]})
        result = alignment.align(net, [{'event_id': 'x1', 'case_id': 'X',
                                        'sequence': 1, 'activity': 'G'}], self.costs, 'X', 'loop')
        self.assertEqual(result['status'], alignment.OPTIMAL)
        self.assertEqual([m['transition_id'] for m in result['moves']], ['go'])

    def test_lexical_tiebreak_prefers_sync_then_transition_id(self):
        net = validate_net(read_json(ROOT / 'examples/nets_small.json')[2])
        result = alignment.align(net, [{'event_id': 'a1', 'case_id': 'Z',
                                        'sequence': 1, 'activity': 'A'}], self.costs, 'Z', 'duplicate_label')
        self.assertEqual(result['cost'], 0)
        self.assertEqual(result['moves'][0]['transition_id'], 't_alpha')
        # 两个候选同为sync同代价同动作数，决胜靠转换ID字典序
        self.assertNotEqual(result['moves'][0]['transition_id'], 't_beta')


if __name__ == '__main__':
    unittest.main()
