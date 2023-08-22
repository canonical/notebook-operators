# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Initialize unit tests
#

"""Setup test environment for unit tests."""

import ops.testing

# enable simulation of container networking
ops.testing.SIMULATE_CAN_CONNECT = True
