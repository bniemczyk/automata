#/usr/bin/env python

import automata

def search_for_string(needle, haystack):

  nfa = automata.NFA(-1)
  nfa.add_transition(-1, automata.NFA.ANY, -1)

  for key in range(256):
    nfa.add_transition(-1, automata.NFA.EPSILON, (key,0))

    for matched in range(len(needle)):
      nfa.add_transition((key,matched), chr(ord(needle[matched]) ^ key), (key,matched+1))

    nfa.add_final_state((key,len(needle)))
    nfa.add_transition((key,len(needle)), automata.NFA.ANY, (key,len(needle)))

  #nfa.to_graph().visualize()
  #print nfa._transitions[-1]
  #print nfa._transitions[(0,0)]
  #print nfa._transitions[(1,1)]
  rv = nfa.execute(haystack)
  #print repr(nfa.bytecode().link())
  return rv
