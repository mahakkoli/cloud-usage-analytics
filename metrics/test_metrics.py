import pytest

from metrics.metrics import MetricError, build_query, list_metrics, query_metric


def test_every_metric_is_documented():
    for m in list_metrics():
        assert m["label"] and m["description"]


def test_total_revenue_matches_the_mart():
    rows = query_metric("revenue", time_grain=None)
    assert rows[0]["revenue"] == pytest.approx(2_193_594, abs=1)


def test_september_2026_revenue_and_active_accounts():
    window = dict(start="2026-09-01", end="2026-09-01")
    assert query_metric("revenue", **window)[0]["revenue"] == pytest.approx(245_328, abs=1)
    assert query_metric("active_accounts", **window)[0]["active_accounts"] == 176


def test_group_by_region_covers_four_regions():
    rows = query_metric("revenue", time_grain="year", group_by=["region"], start="2026-01-01")
    assert {r["region"] for r in rows} == {"us-east", "us-west", "eu-west", "ap-south"}


def test_unknown_metric_is_refused():
    with pytest.raises(MetricError, match="Unknown metric"):
        build_query("profit")


def test_unknown_dimension_is_refused():
    with pytest.raises(MetricError, match="Unknown dimension"):
        build_query("revenue", group_by=["account_name"])


def test_filter_values_are_parameters_not_sql():
    sql, params = build_query("revenue", filters={"plan": "business' or 1=1 --"})
    assert "or 1=1" not in sql
    assert params == ["business' or 1=1 --"]
