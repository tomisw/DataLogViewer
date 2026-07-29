"""Test de humo de `dlv-core`: el paquete se importa y expone `__version__`."""

from __future__ import annotations

import dlv_core


def test_importa_y_tiene_version() -> None:
    assert isinstance(dlv_core.__version__, str)
    assert dlv_core.__version__ != ""
