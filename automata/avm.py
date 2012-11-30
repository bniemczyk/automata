#!/usr/bin/env python

import os
import ctypes

_dllpath = os.path.dirname(__file__)
_dll = ctypes.CDLL('%s/avmjit.so' % (_dllpath))
_runtime = '%s/avmruntime.bc' % (_dllpath)

class StateBuilder(object):
    
    def __init__(self, vm):
        self.vm = vm
        self._builder = _dll.avm_vm_statebuilder_factory(vm._vm)

    def __getattr__(self, name):
        fn = _dll['avm_statebuilder_' + name]
        fn.restype = ctypes.c_void_p
        def _exec_c_func (*args):
            return fn(self._builder, *args)
        return _exec_c_func

    def execute(self, fn):
        self.vm._gc_refs.append(fn)
        fnc = ctypes.CFUNCTYPE(ctypes.c_int)(fn)
        self.vm._gc_refs.append(fnc)
        _dll.avm_statebuilder_execute(self._builder, fnc)

class AVM(object):
    
    def __init__(self):
        self._vm = _dll.avm_vm_factory(_runtime)
        self._gc_refs = []

    def __getattr__(self, name):
        fn = _dll['avm_vm_' + name]
        if name != 'run':
            fn.restype = ctypes.c_void_p
        def _attr_fnc (*args):
            return fn(self._vm, *args)
        return _attr_fnc

    def StateBuilderFactory(self):
        return StateBuilder(self)

    def StateFactory(self, statecompiler):
        callback_t = ctypes.CFUNCTYPE(ctypes.c_void_p)
        callback = callback_t(statecompiler)
        self._gc_refs.append((callback))
        rv = self.codeblock_factory(callback)
        return rv

    def Run(self, startState, inputstr, state_count, tag_count):
        return self.run(startState, inputstr, len(inputstr), state_count, tag_count)

if __name__ == '__main__':
    print 'dll: %s' % (_dll)
    vm = AVM()
    print vm
    builder = vm.StateBuilderFactory()
    print builder
    builder.destroy()
    vm.destroy()
