#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the configuration validators."""

from contextlib import nullcontext as does_not_raise

import pytest

from config_validators import (
    ConfigValidationError,
    validate_named_options_with_default,
    validate_options_with_default,
)

REQUIRED_KEYS = ["limitsKey", "uiName"]


@pytest.mark.parametrize(
    "default, options, options_index_key, required_keys, context_raised",
    [
        # Valid, parsable input
        (
            "1",
            [{"limitsKey": "1", "uiName": "a"}, {"limitsKey": "2", "uiName": "b"}],
            "limitsKey",
            REQUIRED_KEYS,
            does_not_raise(),
        ),
        (
            "b",
            [{"limitsKey": "1", "uiName": "a"}, {"limitsKey": "2", "uiName": "b"}],
            "uiName",
            REQUIRED_KEYS,
            does_not_raise(),
        ),
        # One missing limitsKey
        (
            None,
            [{"limitsKey": "1", "uiName": "a"}, {"uiName": "b"}],
            "limitsKey",
            REQUIRED_KEYS,
            pytest.raises(ConfigValidationError),
        ),
        # One missing uiName
        (
            None,
            [{"limitsKey": "1"}, {"limitsKey": "2", "uiName": "b"}],
            "limitsKey",
            REQUIRED_KEYS,
            pytest.raises(ConfigValidationError),
        ),
        # Default not in vendors
        (
            "not-in-list",
            [{"limitsKey": "1", "uiName": "a"}, {"limitsKey": "2", "uiName": "b"}],
            "limitsKey",
            REQUIRED_KEYS,
            pytest.raises(ConfigValidationError),
        ),
    ],
)
def test_validate_options_with_default(
    default, options, options_index_key, required_keys, context_raised
):
    """Test that validate_gpu_vendors_config raises an exception when a required key is missing."""
    # Test that the function raises a ConfigValidationError when a required key is missing.
    with context_raised:
        validate_options_with_default(default, options, options_index_key, required_keys)


def test_validate_named_options_with_default():
    """Test that validate_named_options_with_default passes with valid input.

    Tests using the gpu as an example case.
    """
    validate_named_options_with_default(
        "nvidia", [{"limitsKey": "nvidia", "uiName": "NVIDIA"}], name="gpu-vendors"
    )
