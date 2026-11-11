import unittest
from itertools import product
from pathlib import Path

from workbench import alignment
from workbench.brute_force import brute_force_optimum
from workbench.domain import validate_net
from workbench.io import read_json

ROOT = Path(__file__).resolve().parents[1]


class ExhaustiveCrossCheckTests(unittest.TestCase):
    def test_small_nets_match_brute_force(self):
        nets = [validate_net(n) for n in read_json(ROOT / 'examples/nets_small.json')]
        rows = read_json(ROOT / 'examples/events_small.json')
        by_case = {}
        for row in rows:
            by_case.setdefault(row['case_id'], []).append(row)
        for log_cost, model_cost in ((1, 1), (2, 3), (5, 1), (0, 0)):
            costs = {'log': log_cost, 'model': model_cost, 'search_limit': 100000}
            for net in nets:
                for cid, events in by_case.items():
                    result = alignment.align(net, events, costs, cid, net['id'])
                    optimum = brute_force_optimum(net, events, costs)
                    if optimum is None:
                        self.assertEqual(result['status'], alignment.UNREACHABLE)
                        continue
                    self.assertEqual(result['status'], alignment.OPTIMAL)
                    self.assertEqual((result['cost'], result['action_count']),
                                     (optimum[0], optimum[1]))

    def test_random_traces_over_linear_net(self):
        net = validate_net({
            'id': 'chain', 'places': ['p0', 'p1', 'p2', 'p3'],
            'initial': ['p0'], 'final': ['p3'],
            'transitions': [
                {'id': 'a', 'label': 'A', 'pre': ['p0'], 'post': ['p1']},
                {'id': 'b', 'label': 'B', 'pre': ['p1'], 'post': ['p2']},
                {'id': 'c', 'label': 'C', 'pre': ['p2'], 'post': ['p3']}]})
        alphabet = ['A', 'B', 'C']
        costs = {'log': 2, 'model': 3, 'search_limit': 100000}
        for width, values in enumerate(product(alphabet, repeat=3)):
            events = [{'event_id': 'r%d-%d' % (width, i), 'case_id': 'R',
                       'sequence': i + 1, 'activity': label} for i, label in enumerate(values)]
            result = alignment.align(net, events, costs, 'R', 'chain')
            optimum = brute_force_optimum(net, events, costs)
            self.assertEqual(result['cost'], optimum[0], values)
            self.assertEqual(result['action_count'], optimum[1], values)


if __name__ == '__main__':
    unittest.main()
