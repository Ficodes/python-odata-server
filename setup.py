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
    description="Python library to create oData v4 APIs",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    packages=("odata_server",),
    include_package_data=True,
    install_requires=read("./requirements.txt"),
    license_files=("LICENSE.txt",),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
