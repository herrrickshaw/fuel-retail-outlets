import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api-data-integration"))


@pytest.fixture
def toll_csv(monkeypatch):
    """Replace the hard-coded ~/Downloads/toll_plazas_cleaned.csv read with an in-memory frame."""
    def _install(df):
        monkeypatch.setattr(pd, "read_csv", lambda *a, **k: df.copy())
    return _install


@pytest.fixture
def ssri_json(monkeypatch, tmp_path):
    """Make the module's hard-coded SSRI json path open a small fixture file instead."""
    def _install(module, pumps):
        p = tmp_path / "ssri.json"
        p.write_text(json.dumps(pumps))
        real_open = open
        monkeypatch.setattr(module, "open", lambda path, *a, **k: real_open(p, *a, **k), raising=False)
    return _install
