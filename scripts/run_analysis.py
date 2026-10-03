"""
Olist E-Commerce Analytics — end-to-end pipeline.

raw CSVs → data quality → fact tables → KPIs → categories / regions → delivery & reviews
→ RFM → cohort retention → CSV exports (+ Power BI tables) → figures & dashboard → key findings.

Metric definitions are identical to sql/03_analytics_queries.sql:
  * scope          — orders with status 'delivered';
  * GMV / revenue  — sum of order_items.price (freight excluded);
  * customer       — customer_unique_id (customer_id is issued per order);
  * late delivery  — delivered date > estimated date (the estimate has no time part).

Usage:  python scripts/run_analysis.py [--data-dir data] [--out-dir outputs]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "translation": "product_category_name_translation.csv",
}

ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "order_delivered_carrier_date",
]

# Fixed display order of RFM segments (most to least valuable).
SEGMENTS = ["Champions", "At Risk", "New High-Value", "New", "Lapsed High-Value", "Lapsed"]

DELAY_BUCKETS = ["on_time", "late_1_3d", "late_4_7d", "late_8d_plus"]

COHORT_WINDOW = ("2017-01", "2018-06")  # cohorts with enough history; 2016 is a test launch
MAX_PERIOD = 6


# =============================================================================
# Load & prepare
# =============================================================================


def load_raw(data_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [f for f in FILES.values() if not (data_dir / f).exists()]
    if missing:
        sys.exit(
            f"Missing files in {data_dir}: {', '.join(missing)}\n"
            "Download the dataset from Kaggle — see data/README.md."
        )
    tables = {name: pd.read_csv(data_dir / f) for name, f in FILES.items()}
    for col in ORDER_DATE_COLS:
        tables["orders"][col] = pd.to_datetime(tables["orders"][col], errors="coerce")
    return tables


def data_quality_report(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        nulls = int(df.isna().sum().sum())
        rows.append(
            {
                "table": name,
                "rows": len(df),
                "cols": df.shape[1],
                "duplicate_rows": int(df.duplicated().sum()),
                "null_cells": nulls,
                "null_pct": round(100 * nulls / df.size, 2),
            }
        )
    return pd.DataFrame(rows)


def delivery_delay(delivered_at: pd.Series, estimated_at: pd.Series) -> pd.Series:
    """Days delivered after the promised date (<= 0 means on time). NaN if not delivered.

    The estimated date carries no time of day, so both sides are compared as dates:
    a parcel delivered at 18:00 on the promised day is on time.
    """
    return (delivered_at.dt.normalize() - estimated_at.dt.normalize()).dt.days


def delay_bucket(delay_days: pd.Series) -> pd.Series:
    bucket = pd.cut(
        delay_days,
        bins=[-np.inf, 0, 3, 7, np.inf],
        labels=DELAY_BUCKETS,
    )
    return bucket.astype("object")


def build_fact(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Order-item level fact for delivered orders, with customer and category."""
    products = tables["products"].merge(tables["translation"], on="product_category_name", how="left")
    fact = (
        tables["items"]
        .merge(tables["orders"], on="order_id", how="inner")
        .merge(tables["customers"], on="customer_id", how="left")
        .merge(
            products[["product_id", "product_category_name", "product_category_name_english"]],
            on="product_id",
            how="left",
        )
    )
    fact = fact[fact["order_status"] == "delivered"].copy()
    fact["category"] = (
        fact["product_category_name_english"].fillna(fact["product_category_name"]).fillna("unknown")
    )
    fact["year_month"] = fact["order_purchase_timestamp"].dt.to_period("M").astype(str)
    return fact


def build_orders(delivered: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """One row per delivered order: revenue, delivery metrics, review score."""
    orders = delivered.groupby("order_id", as_index=False).agg(
        customer_unique_id=("customer_unique_id", "first"),
        customer_state=("customer_state", "first"),
        order_purchase_timestamp=("order_purchase_timestamp", "first"),
        order_delivered_customer_date=("order_delivered_customer_date", "first"),
        order_estimated_delivery_date=("order_estimated_delivery_date", "first"),
        year_month=("year_month", "first"),
        revenue=("price", "sum"),
        freight=("freight_value", "sum"),
        items=("order_item_id", "count"),
    )
    orders["delivery_days"] = (
        orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    orders["delay_days"] = delivery_delay(
        orders["order_delivered_customer_date"], orders["order_estimated_delivery_date"]
    )
    orders["is_late"] = (orders["delay_days"] > 0).astype(float).where(orders["delay_days"].notna())
    orders["delay_bucket"] = delay_bucket(orders["delay_days"])

    # A few orders have several reviews — average them so every order counts once.
    order_review = reviews.groupby("order_id", as_index=False)["review_score"].mean()
    return orders.merge(order_review, on="order_id", how="left")


# =============================================================================
# Metrics
# =============================================================================


def second_order_timing(orders: pd.DataFrame) -> dict:
    """How soon repeat customers place their 2nd order."""
    o = orders.sort_values(["customer_unique_id", "order_purchase_timestamp"])
    o["order_no"] = o.groupby("customer_unique_id").cumcount() + 1
    o["gap_days"] = (
        o.groupby("customer_unique_id")["order_purchase_timestamp"].diff().dt.total_seconds() / 86400
    )
    gaps = o.loc[o["order_no"] == 2, "gap_days"]
    return {
        "second_orders": int(len(gaps)),
        "median_days_to_2nd_order": round(float(gaps.median()), 1),
        "second_order_within_1d_pct": round(float((gaps <= 1).mean() * 100), 1),
        "second_order_within_90d_pct": round(float((gaps <= 90).mean() * 100), 1),
    }


def compute_kpis(delivered: pd.DataFrame, orders: pd.DataFrame) -> dict:
    n_orders = orders["order_id"].nunique()
    per_customer = orders.groupby("customer_unique_id")["order_id"].nunique()
    late = orders["is_late"]
    return {
        "gmv": round(float(delivered["price"].sum()), 2),
        "gmv_incl_freight": round(float((delivered["price"] + delivered["freight_value"]).sum()), 2),
        "orders": int(n_orders),
        "customers": int(per_customer.size),
        "items": int(len(delivered)),
        "aov": round(float(delivered["price"].sum() / n_orders), 2),
        "repeat_purchase_rate_pct": round(float((per_customer >= 2).mean() * 100), 2),
        "avg_delivery_days": round(float(orders["delivery_days"].mean()), 2),
        "median_delivery_days": round(float(orders["delivery_days"].median()), 2),
        "late_delivery_rate_pct": round(float(late.mean() * 100), 2),
        "avg_review_score": round(float(orders["review_score"].mean()), 2),
        "review_on_time": round(float(orders.loc[late == 0, "review_score"].mean()), 2),
        "review_late": round(float(orders.loc[late == 1, "review_score"].mean()), 2),
        "date_min": str(orders["order_purchase_timestamp"].min().date()),
        "date_max": str(orders["order_purchase_timestamp"].max().date()),
        **second_order_timing(orders),
    }


def monthly_dynamics(orders: pd.DataFrame) -> pd.DataFrame:
    monthly = orders.groupby("year_month").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "nunique"),
        customers=("customer_unique_id", "nunique"),
    )
    # Months without delivered orders (e.g. 2016-11) must appear as zeros, not vanish.
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M").astype(str)
    monthly = monthly.reindex(full, fill_value=0).rename_axis("month").reset_index()
    monthly["aov"] = (monthly["revenue"] / monthly["orders"].replace(0, np.nan)).round(2)
    monthly["revenue_mom_pct"] = (monthly["revenue"].pct_change(fill_method=None) * 100).round(1)
    monthly.loc[monthly["month"] < COHORT_WINDOW[0], "revenue_mom_pct"] = np.nan
    return monthly


def category_analysis(delivered: pd.DataFrame) -> pd.DataFrame:
    cat = delivered.groupby("category").agg(
        revenue=("price", "sum"), orders=("order_id", "nunique"), items=("order_id", "count")
    )
    cat = cat.sort_values("revenue", ascending=False).reset_index()
    cat["aov"] = cat["revenue"] / cat["orders"]
    cat["revenue_share_pct"] = 100 * cat["revenue"] / cat["revenue"].sum()
    cat["cumulative_share_pct"] = cat["revenue_share_pct"].cumsum()
    cat["revenue_rank"] = np.arange(1, len(cat) + 1)
    return cat


def region_analysis(orders: pd.DataFrame) -> pd.DataFrame:
    region = orders.groupby("customer_state").agg(
        revenue=("revenue", "sum"),
        orders=("order_id", "nunique"),
        customers=("customer_unique_id", "nunique"),
    )
    region = region.sort_values("revenue", ascending=False).reset_index()
    region["aov"] = region["revenue"] / region["orders"]
    region["revenue_share_pct"] = 100 * region["revenue"] / region["revenue"].sum()
    return region


def delivery_by_state(orders: pd.DataFrame, min_orders: int = 100) -> pd.DataFrame:
    d = orders.dropna(subset=["delay_days"])
    by_state = d.groupby("customer_state").agg(
        orders=("order_id", "nunique"),
        avg_delivery_days=("delivery_days", "mean"),
        late_rate_pct=("is_late", "mean"),
    )
    by_state["late_rate_pct"] *= 100
    return (
        by_state[by_state["orders"] >= min_orders]
        .sort_values("late_rate_pct", ascending=False)
        .reset_index()
    )


def review_by_delay(orders: pd.DataFrame) -> pd.DataFrame:
    r = orders.dropna(subset=["delay_bucket", "review_score"])
    out = r.groupby("delay_bucket").agg(
        orders=("order_id", "count"),
        avg_review_score=("review_score", "mean"),
        negative_review_pct=("review_score", lambda s: (s <= 2).mean() * 100),
    )
    return out.reindex(DELAY_BUCKETS).dropna(how="all").reset_index()


def delivery_outlier_pct(orders: pd.DataFrame) -> float:
    days = orders["delivery_days"].dropna()
    q1, q3 = days.quantile([0.25, 0.75])
    iqr = q3 - q1
    return float(((days < q1 - 1.5 * iqr) | (days > q3 + 1.5 * iqr)).mean() * 100)


def price_outliers(delivered: pd.DataFrame) -> dict:
    prices = delivered["price"]
    q1, q3 = prices.quantile([0.25, 0.75])
    upper = q3 + 1.5 * (q3 - q1)
    out = prices[prices > upper]
    return {
        "price_median": round(float(prices.median()), 2),
        "price_mean": round(float(prices.mean()), 2),
        "price_p95": round(float(prices.quantile(0.95)), 2),
        "price_p99": round(float(prices.quantile(0.99)), 2),
        "iqr_upper": round(float(upper), 2),
        "outlier_items": int(len(out)),
        "outlier_pct": round(100 * len(out) / len(prices), 2),
        "outlier_revenue_share_pct": round(100 * out.sum() / prices.sum(), 2),
    }


# =============================================================================
# RFM
# =============================================================================


def ntile(n_rows: int, n: int = 5) -> np.ndarray:
    """Bucket labels 1..n for rows already sorted ascending — same as SQL NTILE(n)."""
    q, r = divmod(n_rows, n)
    sizes = [q + 1] * r + [q] * (n - r)
    return np.repeat(np.arange(1, n + 1), sizes)


def assign_segment(frequency: pd.Series, r: pd.Series, m: pd.Series) -> pd.Series:
    """
    ~97% of Olist customers buy once, so frequency quintiles would just be random
    tie-breaking among one-time buyers. Instead:
      * repeat buyers (2+ orders) split by recency: Champions / At Risk;
      * one-time buyers split by recency (R 4-5 = recent) and value (M 4-5 = top 40%).
    """
    repeat = frequency >= 2
    recent = r >= 4
    high_value = m >= 4
    conditions = [
        repeat & (r >= 3),
        repeat,
        recent & high_value,
        recent,
        high_value,
    ]
    return pd.Series(
        np.select(conditions, SEGMENTS[:5], default=SEGMENTS[5]), index=frequency.index
    )


def rfm_analysis(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rfm = orders.groupby("customer_unique_id", as_index=False).agg(
        last_order=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("revenue", "sum"),
    )
    rfm["monetary"] = rfm["monetary"].round(2)
    snapshot = rfm["last_order"].max().normalize() + pd.Timedelta(days=1)
    rfm["recency_days"] = (snapshot - rfm["last_order"].dt.normalize()).dt.days

    # Deterministic tie-breaking by customer id, exactly like the SQL version.
    rfm = rfm.sort_values(["recency_days", "customer_unique_id"], ascending=[False, True])
    rfm["R"] = ntile(len(rfm))  # most recent → 5
    rfm = rfm.sort_values(["monetary", "customer_unique_id"])
    rfm["M"] = ntile(len(rfm))  # highest spend → 5
    rfm["F"] = rfm["frequency"].clip(upper=5)
    rfm["segment"] = assign_segment(rfm["frequency"], rfm["R"], rfm["M"])
    rfm = rfm.sort_values("customer_unique_id").reset_index(drop=True)

    seg = rfm.groupby("segment").agg(
        customers=("customer_unique_id", "count"),
        revenue=("monetary", "sum"),
        avg_monetary=("monetary", "mean"),
        avg_frequency=("frequency", "mean"),
        avg_recency_days=("recency_days", "mean"),
    )
    seg = seg.reindex([s for s in SEGMENTS if s in seg.index]).reset_index()
    seg["customer_share_pct"] = 100 * seg["customers"] / seg["customers"].sum()
    seg["revenue_share_pct"] = 100 * seg["revenue"] / seg["revenue"].sum()
    return rfm, seg


# =============================================================================
# Cohorts
# =============================================================================


def cohort_retention(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    act = orders[["customer_unique_id", "order_purchase_timestamp"]].copy()
    act["month"] = act["order_purchase_timestamp"].dt.to_period("M")
    act = act.drop_duplicates(["customer_unique_id", "month"])
    act["cohort"] = act.groupby("customer_unique_id")["month"].transform("min")
    act["period"] = (act["month"] - act["cohort"]).apply(lambda p: p.n)

    long = act.groupby(["cohort", "period"]).size().rename("customers").reset_index()
    sizes = long[long["period"] == 0].set_index("cohort")["customers"]
    long["cohort_size"] = long["cohort"].map(sizes)
    long["retention_pct"] = 100 * long["customers"] / long["cohort_size"]
    long["cohort"] = long["cohort"].astype(str)

    cohorts = pd.period_range(*COHORT_WINDOW, freq="M")
    last_month = act["month"].max()
    pivot = (
        long[long["period"].between(1, MAX_PERIOD)]
        .pivot(index="cohort", columns="period", values="retention_pct")
        .reindex(index=cohorts.astype(str), columns=range(1, MAX_PERIOD + 1))
    )
    # A cohort with nobody returning in an observed month is 0%, not missing;
    # months after the end of the data stay NaN.
    for c in cohorts:
        for p in pivot.columns:
            observed = c + p <= last_month
            if observed and pd.isna(pivot.loc[str(c), p]):
                pivot.loc[str(c), p] = 0.0
            elif not observed:
                pivot.loc[str(c), p] = np.nan
    pivot = pivot.round(2)
    pivot.index.name = "cohort"
    pivot.columns.name = "months_since_first_order"
    cohort_sizes = sizes.rename(index=str).reindex(pivot.index)
    return pivot, long, cohort_sizes


def weighted_m1(long: pd.DataFrame) -> float:
    """Share of customers (all cohorts in the window pooled) who bought again the next month."""
    w = long[long["cohort"].between(*COHORT_WINDOW)]
    base = w.loc[w["period"] == 0, "customers"].sum()
    return float(100 * w.loc[w["period"] == 1, "customers"].sum() / base)


# =============================================================================
# Outputs
# =============================================================================


def export_powerbi_tables(delivered: pd.DataFrame, orders: pd.DataFrame, rfm: pd.DataFrame, out: Path) -> None:
    order_level = orders.merge(
        rfm[["customer_unique_id", "segment", "R", "F", "M"]], on="customer_unique_id", how="left"
    )
    order_level["is_late"] = order_level["is_late"].astype("Int64")
    order_level.drop(columns=["order_delivered_customer_date", "order_estimated_delivery_date"]).to_csv(
        out / "powerbi_orders.csv", index=False
    )
    delivered[
        ["order_id", "order_item_id", "product_id", "seller_id", "category", "customer_unique_id",
         "customer_state", "price", "freight_value", "order_purchase_timestamp", "year_month"]
    ].to_csv(out / "powerbi_order_items.csv", index=False)
    rfm.to_csv(out / "rfm_customers.csv", index=False)


def write_findings(r: dict) -> str:
    k, cat, seg = r["kpis"], r["cat"], r["seg"]
    top_orders = cat.nlargest(15, "orders")
    low_aov, high_aov = top_orders.nsmallest(1, "aov").iloc[0], top_orders.nlargest(1, "aov").iloc[0]
    sp_share = float(r["region"].set_index("customer_state").loc["SP", "revenue_share_pct"])
    rbd = r["review_by_delay"].set_index("delay_bucket")
    s = seg.set_index("segment")
    ps = r["price_stats"]
    peak = r["monthly"].loc[r["monthly"]["revenue"].idxmax()]

    def seg_line(name: str) -> str:
        if name not in s.index:
            return f"- {name}: —"
        row = s.loc[name]
        return (f"- **{name}** — {int(row.customers):,} клиентов ({row.customer_share_pct:.1f}%), "
                f"{row.revenue_share_pct:.1f}% выручки, средний LTV R$ {row.avg_monetary:.0f}")

    lines = [
        "# Key findings",
        "",
        "_Файл генерируется `scripts/run_analysis.py` — не редактировать вручную._",
        "",
        "## KPI (доставленные заказы)",
        f"- Период: {k['date_min']} → {k['date_max']}",
        f"- GMV: R$ {k['gmv']:,.2f} (с доставкой R$ {k['gmv_incl_freight']:,.2f})",
        f"- Заказы: {k['orders']:,} · клиенты: {k['customers']:,} · AOV: R$ {k['aov']:.2f}",
        f"- Repeat purchase rate: {k['repeat_purchase_rate_pct']}% · M1 retention (взвешенно по когортам "
        f"{COHORT_WINDOW[0]}…{COHORT_WINDOW[1]}): {k['m1_retention_pct']:.2f}%",
        f"- Доставка: в среднем {k['avg_delivery_days']} дн., медиана {k['median_delivery_days']} дн.; "
        f"с опозданием {k['late_delivery_rate_pct']}%",
        f"- Средняя оценка отзыва: {k['avg_review_score']}",
        "",
        "## Продажи",
        f"- Пик — {peak['month']} (Black Friday): R$ {peak['revenue']:,.0f}.",
        f"- Топ-5 категорий дают {cat.head(5)['revenue_share_pct'].sum():.1f}% выручки; лидер — "
        f"**{cat.iloc[0]['category']}** ({cat.iloc[0]['revenue_share_pct']:.1f}%).",
        f"- Среди 15 самых массовых категорий минимальный AOV у **{low_aov['category']}** "
        f"(R$ {low_aov['aov']:.2f}, {int(low_aov['orders']):,} заказов), максимальный — у "
        f"**{high_aov['category']}** (R$ {high_aov['aov']:.2f}).",
        f"- Штат SP даёт {sp_share:.1f}% выручки.",
        "",
        "## Доставка и отзывы",
        "- Штаты с наибольшей долей опозданий: "
        + ", ".join(f"{t.customer_state} ({t.late_rate_pct:.1f}%)" for t in r["late_by_state"].head(3).itertuples())
        + ".",
        f"- Оценка: в срок {rbd.loc['on_time', 'avg_review_score']:.2f}, опоздание 1–3 дня "
        f"{rbd.loc['late_1_3d', 'avg_review_score']:.2f}, 8+ дней {rbd.loc['late_8d_plus', 'avg_review_score']:.2f}; "
        f"доля оценок 1–2: {rbd.loc['on_time', 'negative_review_pct']:.0f}% → "
        f"{rbd.loc['late_8d_plus', 'negative_review_pct']:.0f}%.",
        f"- IQR-выбросы по сроку доставки: {r['delivery_outlier_pct']:.1f}% заказов.",
        "",
        "## Клиенты",
        f"- Повторных покупателей {k['second_orders']:,}; медиана до 2-го заказа {k['median_days_to_2nd_order']} дн., "
        f"но {k['second_order_within_1d_pct']}% вторых заказов сделаны в течение суток "
        "(дозаказ, а не возврат клиента).",
        *[seg_line(name) for name in SEGMENTS],
        "",
        "## Цены",
        f"- Медиана цены товара R$ {ps['price_median']}, P95 R$ {ps['price_p95']}, граница IQR R$ {ps['iqr_upper']}.",
        f"- IQR-выбросы: {ps['outlier_pct']}% позиций, но {ps['outlier_revenue_share_pct']}% выручки.",
        "",
    ]
    return "\n".join(lines)


def run(data_dir: Path, out_dir: Path, figures: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Loading data...")
    tables = load_raw(data_dir)

    dq = data_quality_report(tables)
    dq.to_csv(out_dir / "data_quality_report.csv", index=False)
    (
        tables["orders"]["order_status"].value_counts(normalize=True).mul(100).round(2)
        .rename("pct").rename_axis("order_status").to_csv(out_dir / "order_status_share.csv")
    )

    print("Building fact tables...")
    delivered = build_fact(tables)
    orders = build_orders(delivered, tables["reviews"])

    print("Metrics...")
    r: dict = {"delivered": delivered, "orders": orders, "data_quality": dq}
    r["kpis"] = compute_kpis(delivered, orders)
    r["monthly"] = monthly_dynamics(orders)
    r["cat"] = category_analysis(delivered)
    r["region"] = region_analysis(orders)
    r["late_by_state"] = delivery_by_state(orders)
    r["review_by_delay"] = review_by_delay(orders)
    r["delivery_outlier_pct"] = delivery_outlier_pct(orders)
    r["price_stats"] = price_outliers(delivered)
    r["rfm"], r["seg"] = rfm_analysis(orders)
    r["retention_pivot"], r["cohort_long"], r["cohort_sizes"] = cohort_retention(orders)
    r["kpis"]["m1_retention_pct"] = round(weighted_m1(r["cohort_long"]), 2)

    print("Exports...")
    pd.Series(r["kpis"], name="value").rename_axis("metric").to_csv(out_dir / "kpi_summary.csv")
    r["monthly"].to_csv(out_dir / "monthly_sales.csv", index=False)
    r["cat"].round(2).to_csv(out_dir / "category_sales.csv", index=False)
    r["region"].round(2).to_csv(out_dir / "region_sales.csv", index=False)
    r["late_by_state"].round(2).to_csv(out_dir / "delivery_by_state.csv", index=False)
    r["review_by_delay"].round(2).to_csv(out_dir / "review_by_delay.csv", index=False)
    pd.Series(r["price_stats"], name="value").rename_axis("metric").to_csv(out_dir / "price_outliers.csv")
    r["seg"].round(2).to_csv(out_dir / "rfm_segments.csv", index=False)
    r["retention_pivot"].to_csv(out_dir / "retention_heatmap.csv")
    r["cohort_long"].round(2).to_csv(out_dir / "cohort_retention_long.csv", index=False)
    export_powerbi_tables(delivered, orders, r["rfm"], out_dir)

    findings = write_findings(r)
    (out_dir / "key_findings.md").write_text(findings, encoding="utf-8")

    if figures:
        print("Figures...")
        from viz import save_all_figures  # local import: metrics can run without matplotlib

        save_all_figures(r, out_dir / "figures")

    print(findings)
    shown = out_dir.relative_to(ROOT) if out_dir.resolve().is_relative_to(ROOT) else out_dir
    print(f"Done. Outputs → {shown}")
    return r


def _utf8_console() -> None:
    """Windows consoles default to cp1251/cp866 and cannot print "→" or Cyrillic reliably."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--no-figures", action="store_true", help="skip charts and the dashboard")
    args = parser.parse_args()
    run(args.data_dir, args.out_dir, figures=not args.no_figures)


if __name__ == "__main__":
    main()
