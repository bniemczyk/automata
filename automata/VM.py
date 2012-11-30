#!/usr/bin/env python
import copy
import avm
import ctypes
import util

_assocs = util.Associations()
_tag_states = util.Associations()

class DelayedArg(object):
    '''used to generate code on a jit basis'''
    def __init__(self,opGenFunc):
        self.opGenFunc = opGenFunc

    def resolve(self):
        return self.opGenFunc()

    def __str__(self):
        return 'DelayedArg'

class CodeBlock(list):
    def __init__(self, name=None, code_context=None):
        if code_context == None:
            code_context = CodeContext()
            code_context._blocks[name] = self

        self.name = name
        self.last_context = None
        self.code_context = code_context
        self.compiled = None
        self.vm = None
        self.hitcount = 0

    def _optimize_switches(self, minimumLength=2):
      '''
      converts sequences of compare/cjmp to switch instructions
      this must happen BEFORE linking
      minimumLength describes the minum amount of sequential compare/cjmp combinations
      needed to switch to a switch

      AUTOMATICALLY called by compile
      '''
      # locate all the targets of switch statements
      q = util.OneTimeQueue()
      targets = {}
      for i in range(len(self)):
        if isinstance(self[i], Compare) and isinstance(self[i+1], CondJmp):
          q.append(i)

      while q:
        front = q.popleft()
        i = front
        targets[i] = {}
        targets[i][self[i].arg1] = self[i+1].arg1
        while isinstance(self[i+2], Compare) and isinstance(self[i+3], CondJmp):
          i += 2
          targets[front][self[i].arg1] = self[i+1].arg1
          q.remove(i)
        if len(targets[front]) < minimumLength:
          # don't convert single cjmps to switches
          del targets[front]

      # now replace sequences with their switch statements
      # in order for our instruction numbers to be valid, do this
      # in reverse order
      _keys = targets.keys()
      _keys.sort()
      _keys.reverse()
      for i in _keys:
        del self[i:i+(len(targets[i])*2)]
        self.insert(i, Switch(targets[i]))

    def compile(self, vm):
        self.vm = vm

        if self.compiled != None:
            return self.compiled

        self._optimize_switches()
        builder = vm.StateBuilderFactory()
        for op in self:
            op._compile(builder)

        self.compiled = builder.compile()
        builder.destroy()
        return self.compiled

    def __repr__(self):
        rv = []
        for i in range(len(self)):
            rv.append('0x%06x:  %s' % (i, self[i]))

        return '\n'.join(rv)

    def __str__(self):
        return 'UnlinkedCodeBlock'

    def link(self,name=None):
        return self.code_context.link(name, entry_point=self.name)

    def newblock(self, name=None):
        return self.code_context.get_block(name)

    def execute(self, stream, debug=False, state_count=0, tag_count=0):
        if self.vm == None:
            self.vm = avm.AVM()

        def _():
            return self.compile(self.vm)

        state = self.vm.StateFactory(_)
        rslt = int(self.vm.Run(state, stream, state_count, tag_count))
        #self.vm.dump()
        return _assocs.retrieve(rslt) if rslt != 0 else set([])

    def append(self, op):
        if len(self) == 0 and self.name != None and op.debugInfo == None:
            op.debugInfo = 'Begin Block: %s' % (self.name,)

        super(CodeBlock, self).append(op)

    def optimize(self):
        # this used to optimize forks out, but now we don't support forking
        pass

    def undelay(self):
        '''resolves all delayed arguments'''
        i = 0
        while i < len(self):
            op = self[i]
            i += 1
            if hasattr(op, 'arg1'):
                if isinstance(op.arg1,DelayedArg):
                    op.arg1 = op.arg1.resolve()
                if isinstance(op.arg1,CodeBlock):
                    op.arg1.undelay()

class CodeContext(object):
    def __init__(self):
        self._blocks = {}
        self._offset_cache = None

    def copy(self):
        return copy.copy(self)

    def get_block(self, name):
        return self._blocks.setdefault(name, CodeBlock(name,code_context=self))

    def get_blocks(self, entry_point=None):
        if entry_point != None:
            yield (entry_point, self._blocks[entry_point])

        for name in self._blocks:
            if name == entry_point:
                continue
            yield (name, self._blocks[name])

    def get_block_offset(self, name, recache=False, entry_point=None):
        if recache or self._offset_cache == None:
            self._offset_cache = {}
            offset = 0
            for b in self.get_blocks(entry_point=entry_point):
                self._offset_cache[b[0]] = offset
                offset += len(b[1])

        try:
            return self._offset_cache[name]
        except:
            print self._offset_cache
            raise

    def __repr__(self):
        result = []
        for op in self.ops():
            result.append(str(op))
        return '\n'.join(result)

    def fixup_jmps(self,entry_point=None):
        for (name, code) in self.get_blocks(entry_point=entry_point):
            offset = self.get_block_offset(name,entry_point=entry_point)
            for i in code:
                if not isinstance(i, Switch) and isinstance(i, Jmp):
                  if isinstance(i.arg1, CodeBlock):
                      i.arg1 = self.get_block_offset(i.arg1.name,entry_point=entry_point)
                  elif isinstance(i.arg1, int):
                      i.arg1 += offset
                elif isinstance(i, Switch):
                  for j in i.arg1:
                    if isinstance(i.arg1[j], CodeBlock):
                      i.arg1[j] = self.get_block_offset(i.arg1[j].name,entry_point=entry_point)
                    elif isinstance(i.arg1[j], int):
                      i.arg1[j] += offset

    def ops(self,entry_point=None):
        for name, code in self.get_blocks(entry_point=entry_point):
            for i in code:
                yield i

    def link(self,name,entry_point=None):
        self = self.copy()
        self.fixup_jmps(entry_point=entry_point)
        cb = CodeBlock(name)
        for i in self.ops(entry_point=entry_point):
            cb.append(i)
        return cb

class Op(object):
    '''base class for all operations'''
    def _display_nodbg(self, name):
        return name

    def __init__(self, debugInfo=None):
        self.debugInfo = debugInfo

    def _compile(self, builder):
        raise "_compile Not Implemented"

    def _display(self, name):
        if self.debugInfo == None:
            return self._display_nodbg(name)
        else:
            return "%-40s ; %s" % (self._display_nodbg(name), self.debugInfo)
    
class _OpWithArg(Op):
    def __init__(self, arg1, debugInfo=None):
        self.arg1 = arg1
        self.debugInfo = debugInfo

    def _arg_display(self, arg):
        if isinstance(arg, int):
            return '0x%06x' % (arg)
        elif isinstance(arg, str):
            return "'%s'" % (arg)
        else:
            return str(arg)

    def _display_nodbg(self, name):
        return '%-18s    %s' % (name, self._arg_display(self.arg1))

    def _expand_arg(self):
        if isinstance(self.arg1, DelayedArg):
            self.arg1 = self.arg1.resolve()

        return self.arg1

class Match(_OpWithArg):
    '''return a successful match'''
    def exec_step(self, context):
        context.fmatch = True
        context.matchval = self._expand_arg()
        context.multimatchval = None
        context.ip += 1

    def _compile(self, builder):
        builder.match(_assocs.associate((self.arg1,)))

    def __repr__(self):
        return self._display('match')

class Interupt(_OpWithArg):
    '''immediately returns a match before continuing processing'''
    def __init__(self, arg1):
        super(Interupt, self).__init__(arg1)
        self.done = False

    def _compile(self, builder):
      util.warn("Interupts not currently implemented using 'Match'")
      m = Match(slf.arg1)
      return m._compile(builder)

    def __repr__(self):
        return self._display('interupt')

class MultiInterupt(_OpWithArg):
    '''immediately returns a match before continuing processing'''
    def __init__(self, arg1):
        super(MultiInterupt, self).__init__(arg1)
        self.done = False

    def _compile(slf, builder):
      util.warn("Mutli-interupts not currently implemented using 'Multi-Match'")
      m = MultiMatch(self.arg1)
      return m._compile(builder)

    def __repr__(self):
        return self._display('multi-interupt')


class MultiMatch(_OpWithArg):
    '''return multiple successful matches'''
    def exec_step(self, context):
        context.fmatch = True
        context.multimatchval = self._expand_arg()
        context.matchval = None
        context.ip += 1

    def __repr__(self):
        return self._display('multi-match')

    def _compile(self, builder):
        builder.match(_assocs.associate(tuple(self.arg1)))

class Leave(Op):
    '''finish execute'''
    def exec_step(self, context):
        context.ffinished = True

    def __repr__(self):
        return self._display('leave')

    def _compile(self, builder):
        builder.leave()

class Compare(_OpWithArg):
    '''compare [arg2 or cur if missing] to arg1'''
    def exec_step(self, context):
        context.fcmp = context.cur == self._expand_arg()
        context.ip += 1

    def __repr__(self):
        return self._display('compare')

    def _compile(self, builder):
        builder.compare(ctypes.c_char(self.arg1))

class Consume(Op):
    '''consume a character'''
    def exec_step(self, context):
        context.fmatch = False
        context.fconsumed = True
        context.ip += 1

    def __repr__(self):
        return self._display('consume')

    def _compile(self, builder):
        builder.consume()

class Jmp(_OpWithArg):
    '''unconditional jump'''
    def __repr__(self):
        return self._display('jmp')

    def __init__(self, arg1, debugInfo=None):
        super(Jmp, self).__init__(arg1, debugInfo)

    def _compile(self, builder):
        def _():
            cb = self._expand_arg()
            return cb.compile(builder.vm)
            
        builder.branch(builder.vm.StateFactory(_))

class CondJmp(Jmp):
    '''jump if last compare was successful'''
    def __repr__(self):
        return self._display('cjmp')

    def _compile(self, builder):
        def _():
            cb = self._expand_arg()
            return cb.compile(builder.vm)

        builder.cbranch(builder.vm.StateFactory(_))

class Switch(Jmp):
  '''create a jmp table'''
  def __repr__(self):
    rv = 'switch:'
    for i in self.arg1:
      rv += '\n    %s:  %s' % (i, hex(self.arg1[i]) if isinstance(self.arg1[i], int) else self.arg1[i])
    return rv

  def _compile(self, builder):
    def _(tgt):
      def _2():
        _tgt = self.arg1[tgt]
        if isinstance(_tgt, DelayedArg):
          _tgt = _tgt.resolve()
          self.arg1[tgt] = _tgt
        return _tgt.compile(builder.vm)
      return builder.vm.StateFactory(_2)
    _keys = self.arg1.keys()
    _keys = (ctypes.c_char*len(_keys))(*list(_keys))
    _vals = (ctypes.c_void_p*len(_keys))(*list(map(_, _keys)))
    builder.switch(len(_keys), _keys, _vals)

class PyCode(_OpWithArg):
    '''perform a python function'''
    def __init__(self, arg1):
        super(PyCode, self).__init__(arg1)
        self.fn = None

    def __repr__(self):
        return self._display('pycode')

    def _compile(self, builder):
        builder.execute(self.arg1)

class LoadTagV(_OpWithArg):
  '''
  copies the value from one state of a tag to another state
  '''
  def __init__(self, t, src, dst):
    super(LoadTagV, self).__init__((t,src,dst))
    
  def __repr__(self):
    return self._display('ltagv')

  def _compile(self, builder):
    builder.ltagv(self.arg1[0], _tag_states.associate(self.arg1[1]), _tag_states.associate(self.arg1[2]))

class UpdateTagV(_OpWithArg):
  '''
  updates the tag t for the dst state
  '''
  def __init__(self, t, dst):
    super(UpdateTagV, self).__init__((t,dst))
    
  def __repr__(self):
    return self._display('utagv')

  def _compile(self, builder):
    builder.utagv(self.arg1[0], _tag_states.associate(self.arg1[1]))
