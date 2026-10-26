"""Generate synthetic raw data for a fictional usage-based developer cloud.

Writes five raw tables into the `raw` schema of warehouse.duckdb:
accounts, plan_changes, namespaces, daily_usage, invoices.

Built-in patterns (so the metrics have something to find):
- Regions grow at different rates: eu-west grows fastest; us-east is the
  biggest region but grows slowest.
- A few large customers drive most usage (long-tail sizes).
- Accounts expand over time; ~15% churn; some upgrade, a few downgrade.
- Weekday usage is higher than weekend usage.

Built-in messiness (so staging has real work to do):
- Account names with stray spaces; plan and region values in mixed case.
- About 1% exact duplicate rows in daily_usage and a few duplicate invoices.

Prices are invented for this demo and loosely shaped like usage-based
pricing (a monthly base fee plus a charge per million actions and per GB).
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import duckdb
import numpy as np
import pandas as pd

START = date(2025, 4, 1)
END = date(2026, 9, 30)  # 18 full months

PLANS = ["essentials", "business", "enterprise"]
PLAN_BASE_FEE = {"essentials": 100.0, "business": 500.0, "enterprise": 2000.0}
PRICE_PER_MILLION_ACTIONS = {"essentials": 50.0, "business": 45.0, "enterprise": 40.0}
PRICE_PER_GB_MONTH = 0.10

# Relative signup volume at the start vs. the end of the period, per region
REGION_GROWTH = {
    "us-east": (1.0, 1.6),
    "us-west": (0.8, 0.9),
    "eu-west": (0.4, 2.0),
    "ap-south": (0.3, 1.0),
}

NAME_PARTS_A = ["Acme", "Bluefin", "Cargo", "Delta", "Ember", "Fjord", "Granite", "Helix",
                "Iris", "Juniper", "Kestrel", "Lumen", "Maple", "Nimbus", "Orbit", "Pioneer",
                "Quartz", "Redwood", "Summit", "Tidal", "Umbra", "Vertex", "Willow", "Zenith"]
NAME_PARTS_B = ["Robotics", "Labs", "Systems", "Logistics", "Health", "Payments", "Media",
                "Analytics", "Energy", "Freight", "Software", "Bio", "Retail", "Networks"]


def daterange(start: date, end: date):
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def make_accounts(rng: np.random.Generator, n_accounts: int) -> pd.DataFrame:
    days = (END - START).days
    rows = []
    regions = list(REGION_GROWTH)
    for i in range(n_accounts):
        # Pick a signup day, then a region weighted by that region's growth at that time
        t = rng.uniform(0, 0.92)  # leave the last weeks without brand-new signups
        weights = np.array([a + (b - a) * t for a, b in REGION_GROWTH.values()])
        region = rng.choice(regions, p=weights / weights.sum())
        signup = START + timedelta(days=int(t * days))
        plan = rng.choice(PLANS, p=[0.6, 0.3, 0.1])
        name = f"{rng.choice(NAME_PARTS_A)} {rng.choice(NAME_PARTS_B)}"
        rows.append(
            {
                "account_id": f"A{i + 1:04d}",
                "account_name": name,
                "signup_date": signup,
                "region": region,
                "plan": plan,
            }
        )
    return pd.DataFrame(rows)


def make_lifecycles(rng: np.random.Generator, accounts: pd.DataFrame):
    """Per account: size, monthly growth rate, churn date, and plan changes."""
    life = {}
    plan_changes = []
    for acc in accounts.itertuples():
        size = rng.lognormal(mean=11.8, sigma=1.3)  # baseline daily actions; long tail
        size *= {"essentials": 0.6, "business": 1.5, "enterprise": 4.0}[acc.plan]
        growth = rng.normal(0.04, 0.05)  # monthly expansion (can be negative)
        churn_date = None
        if rng.random() < 0.15:
            earliest = acc.signup_date + timedelta(days=60)
            if earliest < END:
                churn_date = earliest + timedelta(days=int(rng.uniform(0, (END - earliest).days)))

        # Plan changes: ~20% upgrade once, ~5% downgrade once
        last_day = churn_date or END
        current = acc.plan
        idx = PLANS.index(current)
        roll = rng.random()
        change = None
        if roll < 0.20 and idx < 2:
            change = PLANS[idx + 1]
        elif roll < 0.25 and idx > 0:
            change = PLANS[idx - 1]
        if change and (last_day - acc.signup_date).days > 45:
            change_date = acc.signup_date + timedelta(
                days=int(rng.uniform(30, (last_day - acc.signup_date).days))
            )
            plan_changes.append(
                {
                    "account_id": acc.account_id,
                    "change_date": change_date,
                    "old_plan": current,
                    "new_plan": change,
                }
            )
        life[acc.account_id] = {"size": size, "growth": growth, "churn_date": churn_date}
    return life, pd.DataFrame(plan_changes)


def make_namespaces(rng: np.random.Generator, accounts: pd.DataFrame, life: dict) -> pd.DataFrame:
    rows = []
    n = 0
    envs = ["prod", "staging", "dev", "batch", "analytics"]
    for acc in accounts.itertuples():
        count = int(rng.integers(1, 6))
        last_day = life[acc.account_id]["churn_date"] or END
        slug = acc.account_name.split()[0].lower()
        for env in envs[:count]:
            n += 1
            offset = 0 if env == "prod" else int(rng.uniform(0, max(1, (last_day - acc.signup_date).days * 0.5)))
            rows.append(
                {
                    "namespace_id": f"N{n:05d}",
                    "account_id": acc.account_id,
                    "namespace_name": f"{slug}-{env}",
                    "created_date": acc.signup_date + timedelta(days=offset),
                    # prod carries most of the load
                    "share": 1.0 if env == "prod" else float(rng.uniform(0.05, 0.4)),
                }
            )
    return pd.DataFrame(rows)


def make_daily_usage(rng: np.random.Generator, namespaces: pd.DataFrame, life: dict) -> pd.DataFrame:
    frames = []
    for ns in namespaces.itertuples():
        info = life[ns.account_id]
        last_day = info["churn_date"] or END
        days = pd.date_range(ns.created_date, last_day, freq="D")
        if len(days) == 0:
            continue
        months_in = (days - pd.Timestamp(ns.created_date)).days / 30.0
        trend = (1 + info["growth"]) ** months_in
        weekday = np.where(days.dayofweek < 5, 1.0, 0.45)
        noise = rng.lognormal(0, 0.25, len(days))
        actions = np.maximum(0, info["size"] * ns.share * trend * weekday * noise).round().astype(int)
        storage = np.round(0.5 + np.cumsum(actions) / 4e7 * ns.share, 2)
        frames.append(
            pd.DataFrame(
                {
                    "namespace_id": ns.namespace_id,
                    "usage_date": days.date,
                    "actions": actions,
                    "storage_gb": storage,
                }
            )
        )
    usage = pd.concat(frames, ignore_index=True)
    dupes = usage.sample(frac=0.01, random_state=int(rng.integers(1e9)))
    return pd.concat([usage, dupes], ignore_index=True).sample(frac=1, random_state=7)


def plan_on(day: date, account_id: str, start_plan: str, changes: pd.DataFrame) -> str:
    if changes.empty:
        return start_plan
    c = changes[(changes.account_id == account_id) & (changes.change_date <= day)]
    return start_plan if c.empty else c.sort_values("change_date").iloc[-1].new_plan


def make_invoices(accounts, namespaces, usage, plan_changes) -> pd.DataFrame:
    clean = usage.drop_duplicates()
    merged = clean.merge(namespaces[["namespace_id", "account_id"]], on="namespace_id")
    merged["invoice_month"] = pd.to_datetime(merged["usage_date"]).dt.to_period("M")
    monthly = (
        merged.groupby(["account_id", "invoice_month"])
        .agg(actions=("actions", "sum"), storage_gb=("storage_gb", "mean"))
        .reset_index()
    )
    start_plan = accounts.set_index("account_id")["plan"]
    rows = []
    for m in monthly.itertuples():
        month_end = m.invoice_month.end_time.date()
        plan = plan_on(month_end, m.account_id, start_plan[m.account_id], plan_changes)
        amount = (
            PLAN_BASE_FEE[plan]
            + m.actions / 1e6 * PRICE_PER_MILLION_ACTIONS[plan]
            + m.storage_gb * PRICE_PER_GB_MONTH
        )
        rows.append(
            {
                "invoice_id": f"INV-{m.account_id}-{m.invoice_month.strftime('%Y%m')}",
                "account_id": m.account_id,
                "invoice_month": m.invoice_month.start_time.date(),
                "plan": plan,
                "amount_usd": round(amount, 2),
            }
        )
    invoices = pd.DataFrame(rows)
    return pd.concat([invoices, invoices.sample(n=5, random_state=3)], ignore_index=True)


def add_messiness(rng: np.random.Generator, accounts: pd.DataFrame) -> pd.DataFrame:
    messy = accounts.copy()
    pick = rng.random(len(messy))
    messy.loc[pick < 0.15, "account_name"] = " " + messy.loc[pick < 0.15, "account_name"] + " "
    messy.loc[pick > 0.80, "plan"] = messy.loc[pick > 0.80, "plan"].str.capitalize()
    messy.loc[(pick > 0.40) & (pick < 0.50), "region"] = messy.loc[(pick > 0.40) & (pick < 0.50), "region"].str.upper()
    return messy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="warehouse.duckdb", help="DuckDB file to write to")
    parser.add_argument("--accounts", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    accounts = make_accounts(rng, args.accounts)
    life, plan_changes = make_lifecycles(rng, accounts)
    namespaces = make_namespaces(rng, accounts, life)
    usage = make_daily_usage(rng, namespaces, life)
    invoices = make_invoices(accounts, namespaces, usage, plan_changes)

    tables = {
        "accounts": add_messiness(rng, accounts),
        "plan_changes": plan_changes,
        "namespaces": namespaces.drop(columns="share"),
        "daily_usage": usage,
        "invoices": invoices,
    }

    con = duckdb.connect(args.db)
    con.execute("create schema if not exists raw")
    for name, df in tables.items():
        con.register("df", df)
        con.execute(f"create or replace table raw.{name} as select * from df")
        con.unregister("df")
        print(f"raw.{name}: {len(df):,} rows")
    con.close()


if __name__ == "__main__":
    main()
