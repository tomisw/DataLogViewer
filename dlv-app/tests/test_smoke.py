"""Test de humo de `dlv-app`: el paquete se importa y expone `__version__`."""

from __future__ import annotations

import dlv_app


def test_importa_y_tiene_version() -> None:
    assert isinstance(dlv_app.__version__, str)
    assert dlv_app.__version__ != ""
