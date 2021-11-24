#!/usr/bin/env python3
# Copyright (c) 2021 Future Internet Consulting and Development Solutions S.L.

import os

from setuptools import setup

import odata_server


def read(fname):
    with open(os.path.join(os.path.dirname(__file__), fname)) as f:
        return f.read()


setup(
    name="odata_server",
    version=odata_server.__version__,
    packages=("odata_server",),
    include_package_data=True,
    install_requires=read("./requirements.txt"),
    license_files=("LICENSE.txt",),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
