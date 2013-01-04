#!/usr/bin/env python

import copy
import VM
from util import OneTimeQueue as _otq
import util
from symath import symbols

class NFA(object):
  EPSILON,ANY = symbols('NFA_ANY NFA_EPSILON')

  def __init__(self, start_state, magic=None):
    self._start_state = start_state
    self._transitions = {}
    self._transitions_to = {}
    self._final_states = set()
    self._has_epsilons = False
    self._bytecode = None
    self._interupt_states = set()
    self._magic = magic
    self._gcrefs = []
    self._tag_assocs = util.Associations()
    self._tcounter = 0
    self._states = set()
    self.choose = lambda a,b: a

  def _choose(self, arglist):
    rv = None
    for i in arglist:
      if rv == None:
        rv = i
      else:
        rv = self.choose(rv, i)

  def transitions_to(self, dst):
    '''
    returns enumerable of (prevstate, t) tuples
    this is super slow and needs to be sped up
    '''
    if dst in self._transitions_to:
      for t in self._transitions_to[dst]:
        for s in self._transitions_to[dst][t]:
          yield (s, t)

  def tag(self, transition, src, dst, tagid=None):
    return self._tag_assocs.associate((transition, src, dst), tagid)

  def is_tagged(self, transition, src, dst):
    return (transition,src,dst) in self._tag_assocs

  def reltags(self, src, cache=None):
    '''
    returns all the tags that are relevant at this state
    cache should be a dictionary and it is updated
    by the function
    '''
    if not self._tag_assocs:
      return set()

    # fucking python and it's terrible support for recursion makes this
    # far more complicated than it needs to be
    if cache == None:
      cache = {}

    q = _otq()
    q.append(src)
    updateq = _otq()


    while q:
      i = q.popleft()
      if i in cache:
        continue

      cache[i] = set()
      for (s,t) in self.transitions_to(i):
        q.append(s)
        if self.is_tagged(t,s,i):
          cache[i].add((self.tag(t,s,i),s, i))
        updateq.appendleft((i, s))

    while updateq:
      i = updateq.popleft()
      cache[i[0]].update(cache[i[1]])

    return cache[src]

  def _add_epsilon_states(self, stateset, gathered_epsilons):
    '''
    stateset is the list of initial states
    gathered_epsilons is a dictionary of (dst: src) epsilon dictionaries
    '''
    for i in list(stateset):
      if i not in gathered_epsilons:
        gathered_epsilons[i] = {}
        q = _otq()
        q.append(i)
        while q:
          s = q.popleft()
          for j in self._transitions.setdefault(s, {}).setdefault(NFA.EPSILON, set()):
            gathered_epsilons[i][j] = s if j not in gathered_epsilons[i] else self.choose(s, j)
            q.append(j)
      stateset.update(gathered_epsilons[i].keys())

  def add_interupt_state(self, state):
    self._interupt_states.add(state)

  def transitions(self, current_states, cached_transitions=None):
    if cached_transitions == None:
      cached_transitions = {}

    rv = set()
    for cs in current_states:
      if cs not in cached_transitions:
        cached_transitions[cs] = set()
        for t in self._transitions.setdefault(cs, {}):
          if t in set([NFA.ANY, NFA.EPSILON]):
            continue
          if self._transitions[cs][t]:
            cached_transitions[cs].add(t)
      rv.update(cached_transitions[cs])
    return rv

  def nextstates(self, current_states, transition):
    rv = set()
    for cs in current_states:
      rv.update(self._transitions.setdefault(cs, {}).setdefault(transition, set()))

    if transition not in (NFA.ANY,NFA.EPSILON):
      for cs in current_states:
        rv.update(self._transitions[cs].setdefault(NFA.ANY, set()))

    return rv

  def _write_transition_code(self, utags, ltags, codeblock):
    utagd = {}
    for i in utags:
      if i[0] in utagd:
        utagd[i[0]] = self.choose(i[1], utagd[i[0]])
      else:
        utagd[i[0]] = i[1]

    ltagd = {}
    for i in ltags:
      if i[0] in utagd:
        continue
      elif i[0] not in ltagd or self.choose(ltagd[i[0]][0], i[1]) == i[1]:
        ltagd[i[0]] = (i[1], i[2])

    for k in utagd:
      codeblock.append(VM.UpdateTagV(k, utagd[k]))

    for k in ltagd:
      codeblock.append(VM.LoadTagV(k, ltagd[k][0], ltagd[k][1]))

  def _transitions_to_dfa_bytecode(self, sources, trn, \
      cached_tcode, \
      debug=False, \
      compiled_states=None, \
      gathered_epsilons=None, \
      cached_transitions=None, \
      reltags_cache=None \
      ):

    key = (trn, tuple(sources))
    if key in cached_tcode:
      return cached_tcode[key]

    # get the stateblock
    sb = self._states_to_dfa_bytecode(sources, tran=trn, debug=debug, \
        compiled_states=compiled_states, gathered_epsilons=gathered_epsilons, \
        cached_transitions=cached_transitions,cached_tcode=cached_tcode, \
        reltags_cache=reltags_cache)

    # build the transition block
    tb = self._bytecode.newblock("Transition 0x%x" % (self._tcounter))
    self._tcounter += 1

    # get a list of tags to emit code for, and reltags to copy previous values from
    tags = set()
    rtags = set()
    for s in sources:
      for d in self._transitions[s].setdefault(trn, set()):
        rtags.update(self.reltags(d, reltags_cache))
        if self.is_tagged(trn, s, d):
          tags.add((self.tag(trn, s, d), d))

    self._write_transition_code(tags, rtags, tb)

    # if tb is empty, just return the stateblock, no need for an extra jmp
    if not tb:
      cached_tcode[key] = sb
      return sb

    # jump to the state block
    tb.append(VM.Jmp(sb))

    # return
    cached_tcode[key] = tb
    return tb

  def _states_to_dfa_bytecode(self, states, \
      tran=None, \
      debug=False, \
      compiled_states=None, \
      gathered_epsilons=None, \
      cached_transitions=None, \
      cached_tcode=None, \
      reltags_cache=None \
      ):
    '''returns the instruction pointer to the bytecode added'''
    pstates = copy.copy(states)

    if reltags_cache == None:
      reltags_cache = {}

    if cached_tcode == None:
      cached_tcode = {}

    if cached_transitions == None:
      cached_transitions = {}

    if gathered_epsilons == None:
      gathered_epsilons = {}

    self._add_epsilon_states(states, gathered_epsilons)

    if tran != None:
      states = self.nextstates(states, tran)
      self._add_epsilon_states(states, gathered_epsilons)

    if self._magic != None:
      states = states.union(self._magic(states))

    tstates = tuple(states)

    # this is used so we only compile each stateset once
    if compiled_states == None:
      compiled_states = {}

    if tstates in compiled_states:
      return compiled_states[tstates]

    # grab the ip from our codeblock
    ip = self._bytecode.newblock(tstates)
    compiled_states[tstates] = ip

    # TODO
    # epsilon transitions are never 'taken' so we need
    # to insert any ltagv/utagv instructions required
    # for all epsilon transitions
    # gathered_epsilons[state] holds a dictionary of dst: src mappings, so we can use that data

    tags = set()
    rtags = set()

    for ts in pstates:
      for dst in gathered_epsilons[ts]:
        rtags.update(self.reltags(dst, reltags_cache))
        src = gathered_epsilons[ts][dst]
        if self.is_tagged(NFA.EPSILON, src, dst):
          tags.add((self.tag(NFA.EPSILON, src, dst), dst))

    self._write_transition_code(tags, rtags, ip)


    # do a multi-match for any final states
    finals = self._final_states.intersection(states)
    if len(finals) > 0:
      ip.append(VM.MultiMatch(finals))

    # do any interupts required
    interupts = self._interupt_states.intersection(states)
    if len(interupts) > 0:
      ip.append(VM.MultiInterupt(interupts))

    # consume a character
    ip.append(VM.Consume())

    ts = self.transitions(states, cached_transitions)

    if debug:
      print 'compiling bytecode for stateset:\n\t%s\n\t0x%x: %s' % (states,ip,(defaults,ts))

    def mkbytecode(t):
      return lambda: self._transitions_to_dfa_bytecode(states, t, cached_tcode, debug=debug, compiled_states=compiled_states, gathered_epsilons=gathered_epsilons, cached_transitions=cached_transitions, reltags_cache=reltags_cache)

    # for any of the non-default states add a conditional jmp
    for k in ts:

      if k in (NFA.ANY, NFA.EPSILON):
        continue

      jmppoint = VM.DelayedArg(mkbytecode(k))
      ip.append(VM.Compare(k))
      ip.append(VM.CondJmp(jmppoint))

    # jmp to default state if there is one, otherwise leave
    defaults = self.nextstates(states, NFA.ANY)
    if len(defaults) > 0:
      jmppoint = VM.DelayedArg(mkbytecode(NFA.ANY))
      ip.append(VM.Jmp(jmppoint))
    else:
      ip.append(VM.Leave())

    # return the instruction pointer
    return ip

  def copy(self):
    rv = NFA(self._start_state)
    rv._final_states = copy.deepcopy(self._final_states)
    rv._has_epsilons = self._has_epsilons
    rv._transitions = {}
    rv._transitions_to = {}
    rv._bytecode = self._bytecode
    for i in self._transitions:
      for j in self._transitions[i]:
        rv._transitions.setdefault(i, {})[j] = self._transitions[i][j].copy()
    for i in self._transitions_to:
      for j in self._transitions_to[i]:
        rv._transitions_to.setdefault(i, {})[j] = self._transitions_to[i][j].copy()
    return rv

  def all_states(self):
    rv = set([self._start_state])
    for s in self._transitions:
      for ns in self._transitions[s].values():
        for nns in ns:
          rv.add(nns)
    return rv

  def add_final_state(self, state):
    self._final_states.add(state)
    self._bytecode = None

  def clear_final_states(self):
    self._final_states = set()
    self._bytecode = None

  def find_epsilon_states(self, state, rv=set()):
    for i in self._transitions.setdefault(state, {}).setdefault(NFA.EPSILON, set()):
      if i not in rv:
        rv.add(i)
        self.find_epsilon_states(i, rv=rv)
    return rv


  def get_starting_states(self):
    epstates = self.find_epsilon_states(self._start_state)
    return set.union(epstates, set([self._start_state]))

  def bytecode(self,debug=False):
    if self._bytecode == None:
      self._bytecode = VM.CodeBlock('EntryPoint')
      self._bytecode.append(VM.Jmp(VM.DelayedArg(lambda: self._states_to_dfa_bytecode(set([self._start_state]), debug=debug))))

    return self._bytecode

  def execute(self, tokenstring, debug=False):
    bc = self.bytecode()
    rv = bc.execute(tokenstring,debug=debug, state_count=len(self.all_states()), tag_count = len(self._tag_assocs))
    return rv

  def add_transition(self, oldstate, token, newstate):
    self._transitions.setdefault(oldstate, {}).setdefault(token, set())
    self._transitions[oldstate][token].add(newstate)

    self._transitions_to.setdefault(newstate, {}).setdefault(token, set())
    self._transitions_to[newstate][token].add(oldstate)

    if token == NFA.EPSILON:
      self._has_epsilons = True
    self._bytecode = None

  def locate_final_states(self):
    dstates = set()
    for i in self._transitions:
      for t in self._transitions[i]:
        dstates = dstates.union(self._transitions[i][t])

    sstates = set([self._start_state])
    for i in self._transitions:
      if len(self._transitions[i]) > 0:
        sstates.add(i)

    self._final_states = dstates.difference(sstates)

    return self._final_states

  def get_transitions(self, oldstate, newstate):
    rv = set()
    for t in self._transitions.setdefault(oldstate, {}):
      if newstate in self._transitions[oldstate][t]:
        rv.add(t)
    return rv

  def get_following_states(self, oldstate):
    rv = set()
    for i in self._transitions.setdefault(oldstate, {}).values():
      rv = set.union(rv, i)
    return rv

  def final_states(self, states):
    return set.intersection(states, self._final_states)

  def to_graph(self):
    from symath.graph import directed
    g = directed.DirectedGraph()

    for s in self.all_states():
      g.add_node(s)
      for t in self._transitions.setdefault(s, {}):
        for dest in self._transitions[s][t]:
          lbl = "'%s'" % (t,)
          if t == NFA.EPSILON:
            lbl = 'E'
          if t == NFA.ANY:
            lbl = '*'

          if self.is_tagged(t, s, dest):
            lbl = "%s/%s" % (lbl, self.tag(t,s,dest))

          g.connect(s, dest, lbl)

    return g

  @staticmethod
  def _test():
    print '----- NFA TEST -----'
    nfa = NFA(0)

    # should match [ab].abcdef
    nfa.add_transition(0, 'a', 1)
    nfa.add_transition(0, 'b', 3)
    nfa.add_transition(1, NFA.ANY, 2)

    rest = "cdef"

    for i in range(len(rest)):
      nfa.add_transition(2+i, rest[i], 3+i)

    nfa.locate_final_states()

    def _exec(s):
      nothing = True
      for i in nfa.execute(s):
        print "execute('%s') = %s" % (s, i)
        nothing = False
      if nothing:
        print "execute('%s') = No Results" % (s)

    #print 'nfa regex: %s' % (nfa.to_regex(hexesc=False))
    #print "execute('abcdefhi') = %s" % (nfa.execute("accdefhi"))
    #print "execute('ccdef') = %s" % (nfa.execute("ccdef"))
    #print "execute('bdef') = %s" % (nfa.execute("bdef"))
    _exec('abcdefhi')
    _exec('ccdef')
    _exec('bdef')

    bc = nfa.bytecode()
    bc = bc.link()
    print bc

if __name__ == '__main__':
  NFA._test()
