#/usr/bin/env python

import automata

def build_nfa(needle):

  nfa = automata.NFA(-1)
  nfa.add_transition(-1, automata.NFA.ANY, -1)

  for key in range(256):
    nfa.add_transition(-1, automata.NFA.EPSILON, (key,0))

    for matched in range(len(needle)):
      nfa.add_transition((key,matched), chr(ord(needle[matched]) ^ key), (key,matched+1))

    nfa.add_final_state((key,len(needle)))
    nfa.add_transition((key,len(needle)), automata.NFA.ANY, (key,len(needle)))

  return nfa

def search_for_string(needle, haystack):
  nfa = build_nfa(needle)
  return nfa.execute(haystack)

if __name__ == '__main__':
  import sys
  import os

  argv = sys.argv[1:]

  if len(argv) < 2:
    print 'usage: xorsearch.py <string to search for> <filelist>'
    exit()

  print 'building nfa'
  nfa = build_nfa(argv[0])
  for fname in argv[1:]:
    print 'scanning %s' % (fname)
    data = open(fname, 'rb').read()
    matches = nfa.execute(data)
    for m in matches:
      print '%s matches with key: 0x%x' % (fname, m[0])
