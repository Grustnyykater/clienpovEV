"""
Olist E-Commerce Analytics — end-to-end pipeline
Loads CSVs → cleans → EDA → RFM → Cohort Retention → exports for Power BI
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
OUT.mkdir(parents=True, exist_ok=True)
FIG.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["axes.titlesize"] = 14


def load_raw() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.read_csv(DATA / "olist_customers_dataset.csv"),
        "orders": pd.read_csv(DATA / "olist_orders_dataset.csv"),
        "items": pd.read_csv(DATA / "olist_order_items_dataset.csv"),
        "payments": pd.read_csv(DATA / "olist_order_payments_dataset.csv"),
        "reviews": pd.read_csv(DATA / "olist_order_reviews_dataset.csv"),
        "products": pd.read_csv(DATA / "olist_products_dataset.csv"),
        "sellers": pd.read_csv(DATA / "olist_sellers_dataset.csv"),
        "translation": pd.read_csv(DATA / "product_category_name_translation.csv"),
    }


def parse_dates(orders: pd.DataFrame) -> pd.DataFrame:
    date_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in date_cols:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")
    return orders


def build_fact(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per order-item for delivered orders with category & customer."""
    orders = parse_dates(tables["orders"].copy())
    items = tables["items"].copy()
    customers = tables["customers"].copy()
    products = tables["products"].merge(
        tables["translation"], on="product_category_name", how="left"
    )

    fact = (
        items.merge(orders, on="order_id", how="inner")
        .merge(customers, on="customer_id", how="left")
        .merge(
            products[
                [
                    "product_id",
                    "product_category_name",
                    "product_category_name_english",
                ]
            ],
            on="product_id",
            how="left",
        )
    )
    fact["category"] = fact["product_category_name_english"].fillna(
        fact["product_category_name"]
    ).fillna("unknown")
    fact["year_month"] = fact["order_purchase_timestamp"].dt.to_period("M").astype(str)
    return fact


def data_quality_report(tables: dict[str, pd.DataFrame], fact: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, df in tables.items():
        rows.append(
            {
                "table": name,
                "rows": len(df),
                "cols": df.shape[1],
                "duplicate_rows": int(df.duplicated().sum()),
                "null_cells": int(df.isna().sum().sum()),
                "null_pct": round(100 * df.isna().sum().sum() / df.size, 2),
            }
        )
    report = pd.DataFrame(rows)
    report.to_csv(OUT / "data_quality_report.csv", index=False)

    status = tables["orders"]["order_status"].value_counts(normalize=True).mul(100).round(2)
    status.to_csv(OUT / "order_status_share.csv", header=["pct"])
    return report


def compute_kpis(fact: pd.DataFrame) -> dict:
    delivered = fact[fact["order_status"] == "delivered"].copy()
    gmv = delivered["price"].sum()
    orders = delivered["order_id"].nunique()
    customers = delivered["customer_unique_id"].nunique()
    aov = gmv / orders if orders else np.nan

    cust_orders = (
        delivered.groupby("customer_unique_id")["order_id"].nunique().reset_index(name="n_orders")
    )
    repeat_rate = (cust_orders["n_orders"] >= 2).mean() * 100

    orders_df = delivered.drop_duplicates("order_id")[
        [
            "order_id",
            "order_purchase_timestamp",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ]
    ].copy()
    orders_df["delivery_days"] = (
        orders_df["order_delivered_customer_date"] - orders_df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400
    orders_df["is_late"] = (
        orders_df["order_delivered_customer_date"] > orders_df["order_estimated_delivery_date"]
    )

    kpis = {
        "gmv": round(float(gmv), 2),
        "orders": int(orders),
        "customers": int(customers),
        "aov": round(float(aov), 2),
        "repeat_purchase_rate_pct": round(float(repeat_rate), 2),
        "avg_delivery_days": round(float(orders_df["delivery_days"].mean()), 2),
        "median_delivery_days": round(float(orders_df["delivery_days"].median()), 2),
        "late_delivery_rate_pct": round(float(orders_df["is_late"].mean() * 100), 2),
        "items": int(len(delivered)),
        "date_min": str(delivered["order_purchase_timestamp"].min().date()),
        "date_max": str(delivered["order_purchase_timestamp"].max().date()),
    }
    pd.Series(kpis).to_csv(OUT / "kpi_summary.csv", header=["value"])
    return kpis, delivered, orders_df


def monthly_dynamics(delivered: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        delivered.groupby("year_month")
        .agg(
            revenue=("price", "sum"),
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
        )
        .reset_index()
    )
    monthly["aov"] = monthly["revenue"] / monthly["orders"]
    monthly.to_csv(OUT / "monthly_sales.csv", index=False)

    fig, ax = plt.subplots()
    ax.plot(monthly["year_month"], monthly["revenue"], marker="o", linewidth=2)
    ax.set_title("Monthly GMV (delivered orders)")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue (BRL)")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIG / "monthly_gmv.png", dpi=150)
    plt.close(fig)
    return monthly


def category_analysis(delivered: pd.DataFrame) -> pd.DataFrame:
    cat = (
        delivered.groupby("category")
        .agg(revenue=("price", "sum"), orders=("order_id", "nunique"), items=("order_id", "count"))
        .reset_index()
    )
    cat["aov"] = cat["revenue"] / cat["orders"]
    cat["revenue_share_pct"] = 100 * cat["revenue"] / cat["revenue"].sum()
    cat = cat.sort_values("revenue", ascending=False)
    cat["revenue_rank"] = range(1, len(cat) + 1)
    cat.to_csv(OUT / "category_sales.csv", index=False)

    top = cat.head(10)
    fig, ax = plt.subplots()
    sns.barplot(data=top, y="category", x="revenue", ax=ax, color="#1f77b4")
    ax.set_title("Top-10 categories by revenue")
    ax.set_xlabel("Revenue (BRL)")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIG / "top_categories.png", dpi=150)
    plt.close(fig)
    return cat


def region_analysis(delivered: pd.DataFrame) -> pd.DataFrame:
    region = (
        delivered.groupby("customer_state")
        .agg(
            revenue=("price", "sum"),
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
        )
        .reset_index()
    )
    region["aov"] = region["revenue"] / region["orders"]
    region["revenue_share_pct"] = 100 * region["revenue"] / region["revenue"].sum()
    region = region.sort_values("revenue", ascending=False)
    region.to_csv(OUT / "region_sales.csv", index=False)

    top = region.head(10)
    fig, ax = plt.subplots()
    sns.barplot(data=top, x="customer_state", y="revenue", ax=ax, color="#2ca02c")
    ax.set_title("Top-10 states by revenue")
    ax.set_xlabel("State")
    ax.set_ylabel("Revenue (BRL)")
    fig.tight_layout()
    fig.savefig(FIG / "top_states.png", dpi=150)
    plt.close(fig)
    return region


def delivery_analysis(orders_df: pd.DataFrame, delivered: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    clean = orders_df.dropna(subset=["delivery_days"]).copy()
    # Outliers: IQR
    q1, q3 = clean["delivery_days"].quantile([0.25, 0.75])
    iqr = q3 - q1
    clean["is_outlier"] = (clean["delivery_days"] < q1 - 1.5 * iqr) | (
        clean["delivery_days"] > q3 + 1.5 * iqr
    )

    state_del = delivered.drop_duplicates("order_id").merge(
        clean[["order_id", "delivery_days", "is_late"]], on="order_id", how="left"
    )
    by_state = (
        state_del.groupby("customer_state")
        .agg(
            orders=("order_id", "nunique"),
            avg_delivery_days=("delivery_days", "mean"),
            late_rate_pct=("is_late", lambda s: 100 * s.mean()),
        )
        .reset_index()
        .query("orders >= 100")
        .sort_values("late_rate_pct", ascending=False)
    )
    by_state.to_csv(OUT / "delivery_by_state.csv", index=False)

    rev = reviews.merge(clean[["order_id", "is_late"]], on="order_id", how="inner")
    rev_cmp = rev.groupby("is_late")["review_score"].agg(["mean", "count"]).reset_index()
    rev_cmp["is_late"] = rev_cmp["is_late"].map({True: "late", False: "on_time"})
    rev_cmp.to_csv(OUT / "review_vs_late.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    sns.histplot(clean["delivery_days"].clip(0, 60), bins=40, ax=axes[0], color="#ff7f0e")
    axes[0].set_title("Delivery time distribution (clipped 0–60 days)")
    axes[0].set_xlabel("Days")
    top_late = by_state.head(10)
    sns.barplot(data=top_late, y="customer_state", x="late_rate_pct", ax=axes[1], color="#d62728")
    axes[1].set_title("Highest late delivery rate by state (≥100 orders)")
    axes[1].set_xlabel("Late rate, %")
    axes[1].set_ylabel("")
    fig.tight_layout()
    fig.savefig(FIG / "delivery_analysis.png", dpi=150)
    plt.close(fig)

    outlier_pct = 100 * clean["is_outlier"].mean()
    return by_state, float(outlier_pct), rev_cmp


def rfm_analysis(delivered: pd.DataFrame) -> pd.DataFrame:
    snapshot = pd.Timestamp("2018-09-01")
    rfm = (
        delivered.groupby("customer_unique_id")
        .agg(
            last_order=("order_purchase_timestamp", "max"),
            frequency=("order_id", "nunique"),
            monetary=("price", "sum"),
        )
        .reset_index()
    )
    rfm["recency_days"] = (snapshot - rfm["last_order"]).dt.days

    # Quintile scores: R — lower days better; F/M — higher better
    rfm["R"] = pd.qcut(rfm["recency_days"].rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    rfm["F"] = pd.qcut(rfm["frequency"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["M"] = pd.qcut(rfm["monetary"].rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    rfm["RFM_score"] = rfm["R"] + rfm["F"] + rfm["M"]

    def segment(row: pd.Series) -> str:
        r, f, m = row["R"], row["F"], row["M"]
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        if r >= 3 and f >= 3 and m >= 3:
            return "Loyal Customers"
        if r >= 4 and f <= 2:
            return "Potential Loyalists"
        if r <= 2 and f >= 3:
            return "At Risk"
        if r <= 2 and f <= 2:
            return "Lost Customers"
        return "Others"

    rfm["segment"] = rfm.apply(segment, axis=1)
    rfm.to_csv(OUT / "rfm_customers.csv", index=False)

    seg = (
        rfm.groupby("segment")
        .agg(
            customers=("customer_unique_id", "count"),
            revenue=("monetary", "sum"),
            avg_monetary=("monetary", "mean"),
            avg_frequency=("frequency", "mean"),
            avg_recency=("recency_days", "mean"),
        )
        .reset_index()
    )
    seg["customer_share_pct"] = 100 * seg["customers"] / seg["customers"].sum()
    seg["revenue_share_pct"] = 100 * seg["revenue"] / seg["revenue"].sum()
    seg = seg.sort_values("revenue", ascending=False)
    seg.to_csv(OUT / "rfm_segments.csv", index=False)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    order = seg.sort_values("customers", ascending=False)["segment"]
    sns.barplot(data=seg, y="segment", x="customers", order=order, ax=axes[0], color="#9467bd")
    axes[0].set_title("Customers by RFM segment")
    sns.barplot(data=seg, y="segment", x="revenue", order=order, ax=axes[1], color="#8c564b")
    axes[1].set_title("Revenue by RFM segment")
    fig.tight_layout()
    fig.savefig(FIG / "rfm_segments.png", dpi=150)
    plt.close(fig)
    return rfm, seg


def cohort_retention(delivered: pd.DataFrame) -> pd.DataFrame:
    cust = (
        delivered.groupby(["customer_unique_id", "order_id"], as_index=False)["order_purchase_timestamp"]
        .min()
    )
    cust["order_month"] = cust["order_purchase_timestamp"].dt.to_period("M")
    first = cust.groupby("customer_unique_id")["order_month"].min().rename("cohort")
    cust = cust.join(first, on="customer_unique_id")
    cust["period"] = (cust["order_month"] - cust["cohort"]).apply(lambda x: x.n)

    cohort = (
        cust.groupby(["cohort", "period"])["customer_unique_id"]
        .nunique()
        .reset_index(name="customers")
    )
    sizes = cohort[cohort["period"] == 0][["cohort", "customers"]].rename(
        columns={"customers": "cohort_size"}
    )
    cohort = cohort.merge(sizes, on="cohort")
    cohort["retention_pct"] = 100 * cohort["customers"] / cohort["cohort_size"]

    # Focus on stable window
    pivot = (
        cohort[
            (cohort["cohort"] >= "2017-01")
            & (cohort["cohort"] <= "2018-06")
            & (cohort["period"] <= 6)
        ]
        .pivot(index="cohort", columns="period", values="retention_pct")
        .round(2)
    )
    pivot.to_csv(OUT / "retention_heatmap.csv")
    cohort.to_csv(OUT / "cohort_retention_long.csv", index=False)

    fig, ax = plt.subplots(figsize=(12, 8))
    sns.heatmap(pivot, annot=True, fmt=".1f", cmap="YlGnBu", ax=ax, cbar_kws={"label": "Retention %"})
    ax.set_title("Cohort Retention Heatmap (% of customers returning)")
    ax.set_xlabel("Months since first purchase")
    ax.set_ylabel("Cohort (first purchase month)")
    fig.tight_layout()
    fig.savefig(FIG / "retention_heatmap.png", dpi=150)
    plt.close(fig)
    return pivot, cohort


def outlier_price_analysis(delivered: pd.DataFrame) -> dict:
    prices = delivered["price"]
    q1, q3 = prices.quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    outliers = delivered[delivered["price"] > upper]
    stats = {
        "price_median": round(float(prices.median()), 2),
        "price_mean": round(float(prices.mean()), 2),
        "price_p95": round(float(prices.quantile(0.95)), 2),
        "price_p99": round(float(prices.quantile(0.99)), 2),
        "iqr_upper": round(float(upper), 2),
        "outlier_items": int(len(outliers)),
        "outlier_pct": round(100 * len(outliers) / len(delivered), 2),
        "outlier_revenue_share_pct": round(100 * outliers["price"].sum() / prices.sum(), 2),
    }
    pd.Series(stats).to_csv(OUT / "price_outliers.csv", header=["value"])

    fig, ax = plt.subplots()
    sns.boxplot(x=prices.clip(upper=prices.quantile(0.99)), ax=ax, color="#17becf")
    ax.set_title("Item price distribution (clipped at P99 for display)")
    ax.set_xlabel("Price (BRL)")
    fig.tight_layout()
    fig.savefig(FIG / "price_outliers.png", dpi=150)
    plt.close(fig)
    return stats


def write_business_insights(
    kpis: dict,
    cat: pd.DataFrame,
    region: pd.DataFrame,
    seg: pd.DataFrame,
    pivot: pd.DataFrame,
    late_by_state: pd.DataFrame,
    rev_cmp: pd.DataFrame,
    price_stats: dict,
    delivery_outlier_pct: float,
) -> str:
    top5 = cat.head(5)
    top5_share = top5["revenue_share_pct"].sum()
    top_cat = cat.iloc[0]
    # High volume low AOV example: among top 15 by orders, pick lowest AOV
    top_orders = cat.sort_values("orders", ascending=False).head(15)
    low_aov_cat = top_orders.sort_values("aov").iloc[0]
    high_aov_cat = top_orders.sort_values("aov", ascending=False).iloc[0]

    sp_share = float(region.loc[region["customer_state"] == "SP", "revenue_share_pct"].sum())
    m1 = float(pivot[1].mean()) if 1 in pivot.columns else float("nan")

    late_row = rev_cmp.set_index("is_late")
    late_score = float(late_row.loc["late", "mean"]) if "late" in late_row.index else float("nan")
    ontime_score = (
        float(late_row.loc["on_time", "mean"]) if "on_time" in late_row.index else float("nan")
    )

    champions = seg[seg["segment"] == "Champions"]
    at_risk = seg[seg["segment"] == "At Risk"]
    lost = seg[seg["segment"] == "Lost Customers"]

    lines = [
        "# Key Findings (generated from analysis)",
        "",
        f"- Period: {kpis['date_min']} → {kpis['date_max']}",
        f"- GMV (delivered): R$ {kpis['gmv']:,.2f}",
        f"- Orders: {kpis['orders']:,} | Customers: {kpis['customers']:,} | AOV: R$ {kpis['aov']:,.2f}",
        f"- Repeat purchase rate: {kpis['repeat_purchase_rate_pct']}%",
        f"- Avg / median delivery: {kpis['avg_delivery_days']} / {kpis['median_delivery_days']} days",
        f"- Late delivery rate: {kpis['late_delivery_rate_pct']}%",
        "",
        "## Categories",
        f"- Top-5 categories generate {top5_share:.1f}% of revenue.",
        f"- Leader: **{top_cat['category']}** — {top_cat['revenue_share_pct']:.1f}% of GMV, "
        f"{int(top_cat['orders']):,} orders, AOV R$ {top_cat['aov']:.2f}.",
        f"- Among high-volume categories, **{low_aov_cat['category']}** has high order volume "
        f"({int(low_aov_cat['orders']):,}) but lower AOV (R$ {low_aov_cat['aov']:.2f}) vs "
        f"**{high_aov_cat['category']}** (AOV R$ {high_aov_cat['aov']:.2f}).",
        "",
        "## Regions",
        f"- São Paulo (SP) alone accounts for ~{sp_share:.1f}% of revenue.",
        f"- Highest late-delivery states (sample): "
        + ", ".join(
            f"{r.customer_state} ({r.late_rate_pct:.1f}%)"
            for r in late_by_state.head(3).itertuples()
        )
        + ".",
        "",
        "## Retention & RFM",
        f"- Average M1 retention across cohorts ≈ {m1:.2f}% (typical for marketplace one-off purchases).",
        f"- Champions: {int(champions['customers'].sum()) if len(champions) else 0} customers, "
        f"{float(champions['revenue_share_pct'].sum()) if len(champions) else 0:.1f}% of revenue.",
        f"- At Risk: {int(at_risk['customers'].sum()) if len(at_risk) else 0} | "
        f"Lost: {int(lost['customers'].sum()) if len(lost) else 0}.",
        "",
        "## Delivery quality",
        f"- Late deliveries average review score {late_score:.2f} vs on-time {ontime_score:.2f}.",
        f"- Delivery-time IQR outliers: {delivery_outlier_pct:.1f}% of orders.",
        "",
        "## Price outliers",
        f"- Item price median R$ {price_stats['price_median']}, P95 R$ {price_stats['price_p95']}.",
        f"- IQR outliers: {price_stats['outlier_pct']}% of items but "
        f"{price_stats['outlier_revenue_share_pct']}% of revenue.",
        "",
    ]
    text = "\n".join(lines)
    (OUT / "key_findings.md").write_text(text, encoding="utf-8")
    return text


def export_powerbi_tables(delivered: pd.DataFrame, rfm: pd.DataFrame, orders_df: pd.DataFrame) -> None:
    """Flattened tables ready for Power BI import."""
    order_level = (
        delivered.groupby(
            [
                "order_id",
                "customer_unique_id",
                "customer_state",
                "order_status",
                "order_purchase_timestamp",
                "year_month",
            ],
            as_index=False,
        )
        .agg(revenue=("price", "sum"), freight=("freight_value", "sum"), items=("order_item_id", "count"))
    )
    order_level = order_level.merge(
        orders_df[["order_id", "delivery_days", "is_late"]], on="order_id", how="left"
    )
    order_level = order_level.merge(
        rfm[["customer_unique_id", "segment", "R", "F", "M", "RFM_score"]],
        on="customer_unique_id",
        how="left",
    )
    order_level.to_csv(OUT / "powerbi_orders.csv", index=False)

    item_level = delivered[
        [
            "order_id",
            "order_item_id",
            "product_id",
            "category",
            "customer_unique_id",
            "customer_state",
            "price",
            "freight_value",
            "order_purchase_timestamp",
            "year_month",
        ]
    ].copy()
    item_level.to_csv(OUT / "powerbi_order_items.csv", index=False)


def main() -> None:
    print("Loading data...")
    tables = load_raw()
    fact = build_fact(tables)
    print("Data quality...")
    dq = data_quality_report(tables, fact)
    print(dq.to_string(index=False))

    print("KPIs...")
    kpis, delivered, orders_df = compute_kpis(fact)
    print(kpis)

    print("Monthly / category / region...")
    monthly_dynamics(delivered)
    cat = category_analysis(delivered)
    region = region_analysis(delivered)

    print("Delivery & outliers...")
    late_by_state, delivery_outlier_pct, rev_cmp = delivery_analysis(
        orders_df, delivered, tables["reviews"]
    )
    price_stats = outlier_price_analysis(delivered)

    print("RFM...")
    rfm, seg = rfm_analysis(delivered)

    print("Cohorts...")
    pivot, _cohort = cohort_retention(delivered)

    print("Exports...")
    export_powerbi_tables(delivered, rfm, orders_df)
    findings = write_business_insights(
        kpis, cat, region, seg, pivot, late_by_state, rev_cmp, price_stats, delivery_outlier_pct
    )
    print("\n" + findings)
    print(f"Done. Outputs → {OUT}")


if __name__ == "__main__":
    main()
