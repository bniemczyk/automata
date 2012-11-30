#!/usr/bin/env python

import automata
import os
import timeit

class FuzzyStringUtility:

  def __init__(self):
    pass

  def _InneficientLevDistance(self, lstA, lstB):
    # trivial cases
    if lstA == lstB: return 0
    if not lstA: return len(lstB)
    if not lstB: return len(lstA)

    subdist = self.LevDistance(lstA[1:], lstB[1:]) + (1 if lstA[0] != lstB[0] else 0)
    shldist = self.LevDistance(lstA[1:], lstB) + 1
    shrdist = self.LevDistance(lstA, lstB[1:]) + 1

    return min(subdist, shldist, shrdist)

  @staticmethod
  def LevDistance(lstA, lstB):
    matrix = zeros((len(lstA)+1,len(lstB)+1),dtype=int)

    # populate the matrix with scores for changes to an empty lsting
    for i in range(len(lstA)+1):
      matrix[i,0] = i

    for i in range(len(lstB)+1):
      matrix[0,i] = i

    for j in range(1, len(lstB)+1):
      for i in range(1, len(lstA)+1):
        if lstA[i-1] == lstB[j-1]: # no operation is required
          matrix[i, j] = matrix[i-1, j-1]
        else:
          matrix[i, j] = min(
            matrix[i-1, j] + 1, # delete
            matrix[i, j-1] + 1, # insert
            matrix[i-1, j-1] + 1 # substitution
            )

    return matrix[len(lstA)-1, len(lstB)-1]

  @staticmethod
  def SpamsumDistance(ssA, ssB):
    '''
    returns the spamsum distance between ssA and ssB
    if they use a different block size, assume maximum distance
    otherwise returns the LevDistance
    '''
    mA = re.match('^(\d+)[:](.*)$', ssA)
    mB = re.match('^(\d+)[:](.*)$', ssB)

    if mA == None or mB == None:
      raise "do not appear to be spamsum signatures"

    if mA.group(1) != mB.group(1):
      return max([len(mA.group(2)), len(mB.group(2))])
    else:
      return LevDistance(mA.group(2), mB.group(2))

  @staticmethod
  def FuzzyMatch(lstA, lstB):
    fLen = float(max(len(lstA), len(lstB)))
    ld = LevDistance(lstA, lstB)
    return 1.0 - ld / fLen

  @staticmethod
  def LevAutomata(term, k, operations = ['insert', 'delete', 'substitute'], search=False):
    nfa = automata.NFA((0,0))

    def _(a,b):
      if a[1] < b[1]:
        return a
      elif b[1] < a[1]:
        return b
      else:
        if b[0] < a[0]:
          return b
        else:
          return a
    
    nfa.choose = _

    if search and 'search' not in operations:
      operations.append('search')

    if 'search' in operations:
      nfa.add_transition((0,0), automata.NFA.ANY, (0,0))

    # each state is a tuple (chars matched, error count)
    for i in range(len(term)):
      c = term[i]

      for e in range(k+1):
        nfa.add_transition((i,e), c, (i+1, e))           # correct character
        if e < k:                          # we can continue, even with an error
          if 'substitute' in operations:
            nfa.add_transition((i,e), automata.NFA.ANY, (i+1, e+1))      # substitution - input mapped to different output
          if 'insert' in operations:
            nfa.add_transition((i,e), automata.NFA.ANY, (i, e+1))       # insertion - input is consumed, no output
          if 'delete' in operations:
            nfa.add_transition((i,e), automata.NFA.EPSILON, (i+1, e+1))    # deletion - no input is consumed

    for i in range(k+1):
      if 'search' in operations:
        nfa.add_transition((len(term), i), automata.NFA.ANY, (len(term), i))
      elif i < k and 'insert' in operations:
        # add allowable errors to account for strings that are too long
        nfa.add_transition((len(term), i), automata.NFA.ANY, (len(term), i + 1))

      # add the final state
      nfa.add_final_state((len(term), i))

    # tag all our transitions out of (0,0) as 1
    for t in nfa._transitions[(0,0)]:
      for s in nfa._transitions[(0,0)][t]:
        if s != (0,0):
          nfa.tag(t, (0,0), s, 0)

    # tag all our transitions to final states
    for d in nfa._final_states:
      for (s,t) in nfa.transitions_to(d):
        if s != d:
          nfa.tag(t, s, d, 1)

    return nfa

def LevAutomata(term, k, operations=['insert','delete','substitute'],search=False):
  return FuzzyStringUtility.LevAutomata(term, k, operations, search)

def LevDistance(lstA, lstB):
  fsu = FuzzyStringUtility()
  return fsu.LevDistance(lstA, lstB)

def FuzzyMatch(lstA, lstB):
  fsu = FuzzyStringUtility()
  return fsu.FuzzyMatch(lstA, lstB)

def SpamsumDistance(ssA, ssB):
  return FuzzyStringUtility(ssA, ssB)

if __name__ == '__main__':
    import pprint
    pp = pprint.PrettyPrinter(depth=6)
  
    sample1 = 'abcd'
    k = 2
  
    if os.path.exists('fuzzystring.nfa'):
      print '----------------------------------'
      print 'Loading Levenshtein Automata from fuzzystring.nfa'
      nfa = fu.loads(open('fuzzystring.nfa').read())
    else:
      print '---------------------------'
      print 'Building Levenshtein Automata from term [%s] with error %d' % (sample1, k)
      nfa = LevAutomata(sample1, k, search=True)

    print 'NFA created (%d states)' % (len(nfa.all_states()))
    eterm = sample1
    print 'final states:\n%s' % (nfa._final_states)
    nfa.to_graph().visualize()
    haystack = eterm[2:] + (eterm * 10 * 2**20) + 'F'
    for i in range(10):
      print 'executing against %f MB string' % (float(len(haystack)) / 2**20)
      rv = set(nfa.execute(haystack,debug=True))
      print 'result = %s' % (rv,)


    print 'saving bytecode text'
    f = open('fuzzystring.bc.txt', 'w')
    f.write(repr(nfa.bytecode().link()))
    f.close()

    if False:
      print 'saving nfa'
      try:
        f = open('fuzzystring.nfa', 'w')
        f.write(fu.dumps(nfa))
        f.close()
      except Exception as ex:
        print ex
        os.unlink('fuzzystring.nfa')
