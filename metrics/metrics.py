"""A lightweight governed metrics layer.

Metrics are defined once in metrics.yml. This module turns a metric request
(metric, time grain, group-by dimensions, filters, date range) into SQL
against the mart, so callers, including the analytics agent, never write SQL.

Safety rules:
- Only metrics and dimensions declared in metrics.yml can be used.
- Filter values and dates are passed as query parameters, never pasted into SQL.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import yaml

SPEC_PATH = Path(__file__).with_name("metrics.yml")
DEFAULT_DB = Path(__file__).resolve().parent.parent / "warehouse.duckdb"
TIME_GRAINS = {"month", "quarter", "year"}
MAX_ROWS = 500


class MetricError(ValueError):
    """Raised for requests the metrics layer does not allow."""


def load_spec(path: Path = SPEC_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def list_metrics(spec: dict | None = None) -> list[dict]:
    spec = spec or load_spec()
    return [{"name": m["name"], "label": m["label"], "description": m["description"]} for m in spec["metrics"]]


def describe_metric(name: str, spec: dict | None = None) -> dict:
    spec = spec or load_spec()
    metric = _get_metric(name, spec)
    return {
        **metric,
        "time_grains": sorted(TIME_GRAINS),
        "dimensions": spec["dimensions"],
    }


def build_query(
    name: str,
    time_grain: str | None = "month",
    group_by: list[str] | None = None,
    filters: dict[str, str | list[str]] | None = None,
    start: str | None = None,
    end: str | None = None,
    spec: dict | None = None,
) -> tuple[str, list]:
    """Return (sql, params) for a metric request. Raises MetricError on bad input."""
    spec = spec or load_spec()
    metric = _get_metric(name, spec)
    group_by = group_by or []
    filters = filters or {}

    allowed = spec["dimensions"]
    for dim in [*group_by, *filters]:
        if dim not in allowed:
            raise MetricError(f"Unknown dimension '{dim}'. Allowed: {', '.join(allowed)}")
    if time_grain is not None and time_grain not in TIME_GRAINS:
        raise MetricError(f"Unknown time grain '{time_grain}'. Allowed: {', '.join(sorted(TIME_GRAINS))}")

    select_cols, group_cols, where, params = [], [], [], []

    if time_grain:
        period = f"date_trunc('{time_grain}', {spec['time_column']})"  # grain is whitelisted above
        select_cols.append(f"{period} as period")
        group_cols.append(period)
    for dim in group_by:
        select_cols.append(dim)
        group_cols.append(dim)
    select_cols.append(f"{metric['sql']} as {metric['name']}")

    for dim, value in filters.items():
        values = value if isinstance(value, list) else [value]
        where.append(f"{dim} in ({', '.join('?' for _ in values)})")
        params.extend(values)
    if start:
        where.append(f"{spec['time_column']} >= ?")
        params.append(_parse_date(start))
    if end:
        where.append(f"{spec['time_column']} <= ?")
        params.append(_parse_date(end))

    sql = f"select {', '.join(select_cols)} from {spec['table']}"
    if where:
        sql += " where " + " and ".join(where)
    if group_cols:
        sql += " group by " + ", ".join(group_cols) + " order by " + ", ".join(group_cols)
    sql += f" limit {MAX_ROWS}"
    return sql, params


def query_metric(name: str, db_path: str | Path = DEFAULT_DB, **request) -> list[dict]:
    """Run a metric request and return rows as dicts."""
    sql, params = build_query(name, **request)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        cursor = con.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, _clean(row))) for row in cursor.fetchall()]
    finally:
        con.close()


def _get_metric(name: str, spec: dict) -> dict:
    for metric in spec["metrics"]:
        if metric["name"] == name:
            return metric
    names = ", ".join(m["name"] for m in spec["metrics"])
    raise MetricError(f"Unknown metric '{name}'. Available metrics: {names}")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MetricError(f"Dates must look like YYYY-MM-DD, got '{value}'") from exc


def _clean(row: tuple) -> tuple:
    """Make values JSON-friendly: dates to ISO strings, floats rounded."""
    out = []
    for v in row:
        if isinstance(v, datetime):
            v = v.date().isoformat()
        elif isinstance(v, date):
            v = v.isoformat()
        elif isinstance(v, float):
            v = round(v, 2)
        out.append(v)
    return tuple(out)
