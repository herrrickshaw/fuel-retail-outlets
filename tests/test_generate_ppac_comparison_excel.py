"""Regression tests for generate_ppac_comparison_excel (static-sweep 2026-10-25)."""
import pandas as pd

import generate_ppac_comparison_excel as g


def _state_company_frames():
    state_df = pd.DataFrame({"State": ["A"], "SSRI_Count": [3], "PPAC_Count": [0]})
    company_df = pd.DataFrame({"Company": ["X"], "SSRI_Count": [3], "SSRI_Percent_%": [100.0]})
    return state_df, company_df


def test_summary_sheet_survives_missing_ppac_data():
    """load_ppac_data() failing leaves ppac_data=None; the summary sheet must
    still be produced (coverage 0 %) instead of crashing with AttributeError."""
    cmp = g.PPACComparison("unused.json", "unused.xlsx")
    cmp.ssri_pumps = [{"id": 1}, {"id": 2}, {"id": 3}]
    cmp.ppac_data = None  # what the object looks like after a failed load
    state_df, company_df = _state_company_frames()
    summary = cmp.create_summary_sheet(state_df, company_df)
    row = summary.set_index("Metric")["Value"]
    assert row["Total SSRI Pumps Extracted"] == 3
    assert row["Total PPAC Outlets (Oct 2021)"] == 0
    assert row["Overall Coverage %"] == "0.00%"


def test_summary_sheet_uses_alternative_count_column():
    cmp = g.PPACComparison("unused.json", "unused.xlsx")
    cmp.ssri_pumps = [{"id": i} for i in range(5)]
    cmp.ppac_data = pd.DataFrame({"State": ["A", "B"], "Total": [6, 4]})
    state_df, company_df = _state_company_frames()
    summary = cmp.create_summary_sheet(state_df, company_df)
    row = summary.set_index("Metric")["Value"]
    assert row["Total PPAC Outlets (Oct 2021)"] == 10
    assert row["Overall Coverage %"] == "50.00%"
