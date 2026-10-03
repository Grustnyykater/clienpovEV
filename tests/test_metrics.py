"""Unit tests for metric logic on small synthetic data (no Kaggle download needed)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_analysis import (  # noqa: E402
    assign_segment,
    cohort_retention,
    delay_bucket,
    delivery_delay,
    monthly_dynamics,
    ntile,
    rfm_analysis,
    second_order_timing,
)

ts = pd.to_datetime


def test_same_day_delivery_is_on_time():
    delivered = pd.Series(ts(["2018-01-10 18:30", "2018-01-11 09:00", None]))
    estimated = pd.Series(ts(["2018-01-10", "2018-01-10", "2018-01-10"]))
    delay = delivery_delay(delivered, estimated)
    assert delay.iloc[0] == 0  # delivered later that day — still on time
    assert delay.iloc[1] == 1
    assert np.isnan(delay.iloc[2])  # not delivered → unknown, not "on time"


def test_delay_buckets():
    buckets = delay_bucket(pd.Series([-5, 0, 1, 3, 4, 7, 8, np.nan]))
    assert buckets.tolist()[:7] == [
        "on_time", "on_time", "late_1_3d", "late_1_3d", "late_4_7d", "late_4_7d", "late_8d_plus",
    ]
    assert pd.isna(buckets.iloc[7])


@pytest.mark.parametrize("n", [5, 7, 12, 101])
def test_ntile_matches_sql_semantics(n):
    labels = ntile(n)
    sizes = np.bincount(labels)[1:]
    assert len(labels) == n
    assert sizes.max() - sizes.min() <= 1
    assert list(sizes) == sorted(sizes, reverse=True)  # larger groups come first, like NTILE
    assert list(labels) == sorted(labels)


def test_segments():
    freq = pd.Series([3, 2, 1, 1, 1, 1])
    r = pd.Series([3, 2, 5, 4, 1, 3])
    m = pd.Series([1, 5, 4, 3, 5, 3])
    assert assign_segment(freq, r, m).tolist() == [
        "Champions", "At Risk", "New High-Value", "New", "Lapsed High-Value", "Lapsed",
    ]


def _orders(rows):
    df = pd.DataFrame(rows, columns=["order_id", "customer_unique_id", "order_purchase_timestamp", "revenue"])
    df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"], format="ISO8601")
    df["year_month"] = df["order_purchase_timestamp"].dt.to_period("M").astype(str)
    return df


def test_rfm_one_time_buyers_never_become_repeat_segments():
    orders = _orders(
        [(f"o{i}", f"c{i}", f"2018-0{1 + i % 8}-15", 10.0 * (i + 1)) for i in range(40)]
        + [("x1", "c0", "2018-08-20", 50.0)]
    )
    rfm, seg = rfm_analysis(orders)
    one_time = rfm[rfm["frequency"] == 1]
    assert not one_time["segment"].isin(["Champions", "At Risk"]).any()
    assert rfm.loc[rfm["customer_unique_id"] == "c0", "segment"].item() == "Champions"
    assert seg["customers"].sum() == 40
    assert seg["revenue_share_pct"].sum() == pytest.approx(100)


def test_cohort_zero_vs_unobserved():
    orders = _orders(
        [
            ("a1", "A", "2018-04-05", 1), ("a2", "A", "2018-05-10", 1),
            ("b1", "B", "2018-04-20", 1),
            ("c1", "C", "2018-06-01", 1),
        ]
    )
    pivot, long, sizes = cohort_retention(orders)
    assert sizes["2018-04"] == 2
    assert pivot.loc["2018-04", 1] == 50.0  # A came back
    assert pivot.loc["2018-04", 2] == 0.0  # observed month, nobody returned
    assert np.isnan(pivot.loc["2018-04", 3])  # 2018-07 is after the data ends


def test_monthly_fills_gaps():
    orders = _orders([("o1", "a", "2016-10-01", 5), ("o2", "b", "2016-12-01", 7)])
    monthly = monthly_dynamics(orders)
    assert monthly["month"].tolist() == ["2016-10", "2016-11", "2016-12"]
    assert monthly.loc[1, "revenue"] == 0


def test_second_order_timing():
    orders = _orders(
        [
            ("1", "a", "2018-01-01 10:00", 1), ("2", "a", "2018-01-01 12:00", 1),
            ("3", "b", "2018-01-01", 1), ("4", "b", "2018-03-02", 1), ("5", "b", "2018-05-01", 1),
            ("6", "c", "2018-01-01", 1),
        ]
    )
    t = second_order_timing(orders)
    assert t["second_orders"] == 2
    assert t["second_order_within_1d_pct"] == 50.0
