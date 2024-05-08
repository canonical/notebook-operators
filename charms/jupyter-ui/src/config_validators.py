#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tools for validating configuration options."""

import dataclasses
from dataclasses import field
from typing import List, Union

OPTIONS_LOOKUP = {
    "gpu-vendors": {
        "required_keys": ["limitsKey", "uiName"],
        "option_index_key": "limitsKey",
    },
    "affinity-options": {
        "required_keys": ["configKey", "displayName", "affinity"],
        "option_index_key": "configKey",
    },
    "tolerations-options": {
        "required_keys": ["groupKey", "displayName", "tolerations"],
        "option_index_key": "groupKey",
    },
}

VALID_GPU_NUMS = [0, 1, 2, 4, 8]


class ConfigValidationError(Exception):
    """Raised when validate of a configuration option fails."""

    pass


@dataclasses.dataclass
class OptionsWithDefault:
    """A class to store configuration options with default values."""

    default: str = ""
    options: List[dict] = field(default_factory=list)


def validate_options_with_default(
    default: Union[str, None], options: List[dict], option_index_key: str, required_keys: List[str]
) -> bool:
    """Validate configuration specified by a list of options and their default.

    Validation function for options like the affinity, gpu, or tolerations options which accept
    a list of options dicts, each with some required keys, and a default value that points at one
    of those options by an index key.

    Raises ConfigValidationError if the configuration is invalid (missing a key, the default does
    not exist in the list, etc), otherwise returns True.

    Args:
        default: A key corresponding to the options entry that should be selected by default
        options: A list of dictionaries, each containing the configuration options with some
                 required keys
        option_index_key: The field in each `option` dict that is used as its index key
        required_keys: A list of keys that each `option` dict must have
    """
    for option in options:
        if not isinstance(option, dict):
            raise ConfigValidationError(f"Configuration option {option} is not a dictionary.")
        for key in required_keys:
            if key not in option:
                raise ConfigValidationError(
                    f"Configuration option {option} missing required key: {key}"
                )

    if default and not any(default == option[option_index_key] for option in options):
        raise ConfigValidationError(
            f"Default selection {default} not found in the list of options."
        )

    return True


def validate_named_options_with_default(
    default: Union[str, None], options: List[dict], name: str
) -> bool:
    """Wrap validate_options_with_default to set up the validator by config name.

    This is a convenience function that automatically sets option_index_key and required_keys
    for validate_options_with_default().  See validate_options_with_default() for more information.

    Args:
        default: A key corresponding to the options entry that should be selected by default
        options: A list of dictionaries, each containing the configuration options with some
                 required keys
        name: the name of the configuration option to validate, for example "gpu-vendors"
    """
    return validate_options_with_default(
        default,
        options,
        OPTIONS_LOOKUP[name]["option_index_key"],
        OPTIONS_LOOKUP[name]["required_keys"],
    )


def parse_gpu_num(num_gpu: str) -> str:
    """Return the parsed value for the gpu-number-default configuration."""
    num_gpu = int(num_gpu)
    if num_gpu == 0:
        return "none"
    try:
        if num_gpu not in VALID_GPU_NUMS:
            raise ConfigValidationError(
                f"Invalid value for gpu-number-default: {num_gpu}. Must be one of {VALID_GPU_NUMS}."
            )
        return str(num_gpu)
    except ValueError:
        raise ConfigValidationError("Invalid value for gpu-number-default.")
