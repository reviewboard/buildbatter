#!/usr/bin/env python

from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages


VERSION = "0.1"


setup(name="BuildBatter",
      version=VERSION,
      license="MIT",
      description="Buildbot utility scripts used in Review Board",
      packages=find_packages(),
      install_requires=[
          'virtualenv>=1.0',
          'buildbot>=0.7.8',
      ],
      maintainer="Christian Hammond",
      maintainer_email="chipx86@chipx86.com"
)
