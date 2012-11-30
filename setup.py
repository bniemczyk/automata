#!/usr/bin/env python

from setuptools import setup, Extension, command
from setuptools.dist import Distribution
import os

_depends = '''
symath
'''

class MyDist(Distribution):
  def has_ext_modules(self):
    return True

setup( \
  name='automata', \
  version='0.1', \
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
  distclass = MyDist, \
  classifiers = [ \
    'Development Status :: 3 - Alpha', \
    'Intended Audience :: Developers', \
    'Intended Audience :: Science/Research', \
    'License :: OSI Approved :: BSD License', \
    'Topic :: Scientific/Engineering :: Mathematics' \
    ]
  )
