import unittest
from automata import *
import os

class TestAutomata(unittest.TestCase):

  def setUp(self):
    pass

  def test_nfa(self):
    NFA._test()

  def test_fuzzystring(self):
    import pprint
    pp = pprint.PrettyPrinter(depth=6)
  
    sample1 = 'abcd'
    k = 2
  
    print '---------------------------'
    print 'Building Levenshtein Automata from term [%s] with error %d' % (sample1, k)
    nfa = fuzzystring.LevAutomata(sample1, k, search=True)

    print 'NFA created (%d states)' % (len(nfa.all_states()))
    eterm = sample1
    print 'final states:\n%s' % (nfa._final_states)
    haystack = eterm[2:] + (eterm * 10 * 2**20) + 'F'
    for i in range(2):
      print 'executing against %f MB string' % (float(len(haystack)) / 2**20)
      rv = set(nfa.execute(haystack,debug=True))
      print 'result = %s' % (rv,)

    if False:
      print 'saving nfa'
      try:
        f = open('fuzzystring.nfa', 'w')
        f.write(fu.dumps(nfa))
        f.close()
      except Exception as ex:
        print ex
        os.unlink('fuzzystring.nfa')

  def test_failure_case_1(self):
    auto = fuzzystring.LevAutomata('test string', 2)
    rv = auto.execute('teststring')
    print rv
    self.assertTrue((11,1) in rv)

  def test_failure_case_2(self):
    auto = fuzzystring.LevAutomata('test you', 1)
    rv = auto.execute('test yu', debug=True)
    print repr(auto.bytecode().link())
    if len(rv) == 0:
      auto.to_graph().visualize()
    self.assertEqual(len(rv), 1)

  def test_state_hooks(self):
    nfa = NFA(-1)
    nfa.add_transition(-1, 'a', 0)
    nfa.add_transition(0, 'a', 0)
    def _h():
      _h.count += 1
      return _h.count
    _h.count = 0
    nfa.add_state_hook(0, _h)
    nfa.execute('aaaba')
    self.assertEqual(_h.count, 3)
