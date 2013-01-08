import unittest
import automata.xorsearch

class TestXorSearch(unittest.TestCase):

  def setUp(self):
    pass

  def _xor_string(self, key, string):
    return ''.join(map(lambda xored: chr(xored ^ key), map(ord, string)))

  def test_simple_string(self):
    rv = automata.xorsearch.search_for_string('simple string', 'find a simple string in this')
    self.assertEqual(len(rv), 1)
    self.assertEqual(rv[0][0], 0)

  def test_nomatch(self):
    rv = automata.xorsearch.search_for_string('this should not match', 'some random longer string string string string')
    self.assertEqual(len(rv), 0)

  def test_xorred_string(self):
    haystack = self._xor_string(1, 'find a xorred string here')
    rv = automata.xorsearch.search_for_string('xorred string', haystack)
    self.assertEqual(len(rv), 1)
    self.assertEqual(rv[0][0], 1)
