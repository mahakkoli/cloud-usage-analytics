"""MCP server exposing the governed metrics layer to an AI agent.

The agent gets exactly three tools and no raw SQL access, so every number
it reports comes from a definition in metrics/metrics.yml.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from metrics.metrics import MetricError, describe_metric, list_metrics, query_metric  # noqa: E402

mcp = MCPServer("cloud-usage-metrics")


@mcp.tool(name="list_metrics")
def list_metrics_tool() -> list[dict]:
    """List every governed metric with its label and description.

    Call this first to find which metric answers the user's question.
    """
    return list_metrics()


@mcp.tool(name="describe_metric")
def describe_metric_tool(name: str) -> dict:
    """Show a metric's exact definition, the time grains it supports, and the
    dimensions it can be grouped or filtered by. Use it to explain an answer."""
    try:
        return describe_metric(name)
    except MetricError as exc:
        return {"error": str(exc)}


@mcp.tool(name="query_metric")
def query_metric_tool(
    name: str,
    time_grain: str | None = "month",
    group_by: list[str] | None = None,
    filters: dict[str, str | list[str]] | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Get numbers for one governed metric. This is the only way to get data.

    Args:
        name: metric name from list_metrics, e.g. "revenue".
        time_grain: "month", "quarter", "year", or null for a single total.
        group_by: dimensions to break down by, e.g. ["region"] or ["plan"].
        filters: dimension values to keep, e.g. {"plan": "business"} or {"region": ["eu-west", "us-east"]}.
        start: first month to include, as YYYY-MM-DD (data runs 2025-04-01 to 2026-09-01).
        end: last month to include, as YYYY-MM-DD.
    """
    try:
        rows = query_metric(
            name, time_grain=time_grain, group_by=group_by, filters=filters, start=start, end=end
        )
        return {"metric": name, "definition": describe_metric(name)["sql"], "rows": rows}
    except MetricError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run()
