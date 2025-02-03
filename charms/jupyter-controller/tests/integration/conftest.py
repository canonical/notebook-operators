#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""
Pytest configuration and fixture setup.

This module provides pytest options for configuring the test environment.
"""

from _pytest.config.argparsing import Parser


def pytest_addoption(parser: Parser):
    """Add custom command-line options for pytest.

    Args:
        parser (Parser): The pytest argument parser.
    """
    parser.addoption(
        "--charm-path",
        help="Path to directory where charm files are stored.",
    )
