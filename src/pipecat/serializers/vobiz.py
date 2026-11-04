#
# Copyright (c) 2026, Vobiz
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Deprecated import path. Use ``pipecat_vobiz`` instead."""

import warnings

from pipecat_vobiz import VobizFrameSerializer, parse_vobiz_start

warnings.warn(
    "pipecat.serializers.vobiz is deprecated; import from pipecat_vobiz instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["VobizFrameSerializer", "parse_vobiz_start"]
