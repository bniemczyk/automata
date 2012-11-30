#!/usr/bin/env python

from setuptools import setup, Extension

_depends = '''
symath
'''

setup( \
  name='automata', \
  version='git', \
  description='finite automata for python', \
  author='Brandon Niemczyk', \
  author_email='brandon.niemczyk@gmail.com', \
  url='http://github.com/bniemczyk/automata', \
  packages=['automata'], \
	package_data={'automata': ['avmruntime.bc', 'avmjit.so']}, \
  include_package_data=True, \
  test_suite='tests', \
  license='BSD', \
  install_requires=_depends, \
  zip_safe = False, \
  classifiers = [ \
    'Development Status :: 3 - Alpha', \
    'Intended Audience :: Developers', \
    'Intended Audience :: Science/Research', \
    'License :: OSI Approved :: BSD License', \
    'Topic :: Scientific/Engineering :: Mathematics' \
    ]
  )
