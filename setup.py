#!/usr/bin/env python

import distutils
import setuptools
from setuptools import setup, Extension, Command
from setuptools.dist import Distribution
from distutils.command.build import build
import os

_depends = '''
symath
'''

class Clean(Command):

  user_options = []

  def run(self):
    os.system('make -C automata clean')
    os.system('rm -rf build')

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass


class BuildCmd(build):
  def run(self):
    os.system("make -C automata")
    build.run(self)

class BuildExtCmd(build):
  extensions = []

  def run(self):
    os.system("make -C automata")

  def get_source_files(self):
    return []

class MyDist(Distribution):
  def has_ext_modules(self):
    return True

setup( \
  name='automata', \
  version='git', \
  description='finite automata for python', \
  author='Brandon Niemczyk', \
  author_email='brandon.niemczyk@gmail.com', \
  url='http://github.com/bniemczyk/automata', \
  packages=['automata'], \
	package_data={'automata': ['avmruntime.bc', 'avmjit.so', 'avmjit.dll']}, \
  include_package_data=True, \
  test_suite='tests', \
  license='BSD', \
  cmdclass = { 'build': BuildCmd, 'build_ext': BuildExtCmd, 'clean': Clean }, \
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
