"""Test de humo de `dlv-api`: el paquete se importa y expone `__version__`."""

from __future__ import annotations

import dlv_api


def test_importa_y_tiene_version() -> None:
    assert isinstance(dlv_api.__version__, str)
    assert dlv_api.__version__ != ""
