"""Every script in api-data-integration/ must at least import (static-sweep 2026-10-25).

The repo had no requirements.txt, so a fresh environment could not import the
13 scripts that depend on requests / bs4 / pdfplumber.  Network-bound modules
are imported with their main guard intact, so nothing is fetched here.
"""
import importlib
import os

import pytest

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api-data-integration")
MODULES = sorted(
    f[:-3] for f in os.listdir(HERE)
    if f.endswith(".py") and f not in {"crawl_ssri.py"}  # crawl_ssri runs a crawl at import time
)


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    importlib.import_module(name)
