"""
Charts for the Olist analysis: one consistent style, individual figures and
a one-page summary dashboard (outputs/figures/dashboard.png).

Every plot_* function draws into a given Axes, so the same chart is reused
both as a standalone figure and as a dashboard panel.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter  # noqa: E402

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

# --- palette: two categorical slots + a one-hue sequential ramp ---------------
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e1"
BLUE = "#2a78d6"  # main series / "good" state
ORANGE = "#eb6834"  # late deliveries / second series
BLUE_RAMP = LinearSegmentedColormap.from_list(
    "blue_seq", ["#eef5fd", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]
)

MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def set_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "font.family": ["Segoe UI", "DejaVu Sans"],
            "font.size": 10,
            "text.color": TEXT,
            "axes.labelcolor": TEXT_2,
            "axes.edgecolor": GRID,
            "axes.linewidth": 1,
            "axes.titlesize": 12,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "grid.color": GRID,
            "grid.linewidth": 1,
            "xtick.color": TEXT_2,
            "ytick.color": TEXT_2,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "legend.frameon": False,
            "legend.fontsize": 9,
        }
    )


def brl(x: float, _pos=None) -> str:
    """Compact Brazilian real: R$ 1.2M / R$ 350K / R$ 75."""
    if abs(x) >= 1e6:
        return f"R$ {x / 1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"R$ {x / 1e3:.0f}K"
    return f"R$ {x:.0f}"


def _month_label(d) -> str:
    return f"{MONTHS_RU[d.month - 1]} {d:%y}"


def _value_grid(ax, axis: str = "y") -> None:
    ax.grid(axis=axis, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def _bar_labels(ax, bars, labels) -> None:
    """Value labels just past the end of horizontal bars."""
    for bar, text in zip(bars, labels):
        ax.annotate(
            text,
            (bar.get_width(), bar.get_y() + bar.get_height() / 2),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=TEXT_2,
        )


# --- charts --------------------------------------------------------------------


def plot_monthly_gmv(ax, monthly: pd.DataFrame) -> None:
    # 2016 is the platform's test launch (a few hundred orders, an empty November) — skip it
    m = monthly[monthly["month"] >= "2017-01"].reset_index(drop=True)
    x = pd.to_datetime(m["month"])
    y = m["revenue"]
    ax.plot(x, y, color=BLUE, linewidth=2, solid_capstyle="round", solid_joinstyle="round")
    ax.fill_between(x, y, color=BLUE, alpha=0.10, linewidth=0)
    ax.scatter(x.iloc[[-1]], y.iloc[[-1]], s=50, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)

    peak = int(y.idxmax())
    ax.scatter(x.iloc[[peak]], y.iloc[[peak]], s=50, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    ax.annotate(
        f"Black Friday · {_month_label(x[peak])}\n{brl(y[peak])}",
        (x[peak], y[peak]),
        xytext=(-10, 6),
        textcoords="offset points",
        ha="right",
        fontsize=9,
        color=TEXT_2,
    )
    ax.annotate(
        f"{_month_label(x.iloc[-1])}\n{brl(y.iloc[-1])}",
        (x.iloc[-1], y.iloc[-1]),
        xytext=(0, 10),
        textcoords="offset points",
        ha="center",
        fontsize=9,
        color=TEXT_2,
    )
    ax.set_title("Выручка (GMV) по месяцам")
    ax.yaxis.set_major_formatter(FuncFormatter(brl))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _month_label(mdates.num2date(v))))
    ax.set_ylim(0, y.max() * 1.22)
    ax.margins(x=0.03)
    _value_grid(ax, "y")


def plot_top_categories(ax, cat: pd.DataFrame, n: int = 10) -> None:
    top = cat.head(n).iloc[::-1]
    names = top["category"].str.replace("_", " ")
    bars = ax.barh(names, top["revenue"], height=0.6, color=BLUE)
    _bar_labels(ax, bars, [f"{brl(r)} · {s:.1f}%" for r, s in zip(top["revenue"], top["revenue_share_pct"])])
    ax.set_title(f"Топ-{n} категорий по выручке")
    ax.xaxis.set_major_locator(MaxNLocator(4))
    ax.xaxis.set_major_formatter(FuncFormatter(brl))
    ax.set_xlim(0, top["revenue"].max() * 1.5)
    _value_grid(ax, "x")


def plot_top_states(ax, region: pd.DataFrame, n: int = 10) -> None:
    top = region.head(n)
    bars = ax.bar(top["customer_state"], top["revenue"], width=0.6, color=BLUE)
    for bar, share in zip(bars, top["revenue_share_pct"]):
        ax.annotate(
            f"{share:.1f}%",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=TEXT_2,
        )
    ax.set_title(f"Топ-{n} штатов по выручке (подпись — доля GMV)")
    ax.yaxis.set_major_formatter(FuncFormatter(brl))
    _value_grid(ax, "y")


def plot_late_by_state(ax, by_state: pd.DataFrame, overall_late_pct: float, n: int = 10) -> None:
    top = by_state.head(n).iloc[::-1]
    bars = ax.barh(top["customer_state"], top["late_rate_pct"], height=0.6, color=ORANGE)
    _bar_labels(ax, bars, [f"{v:.1f}%" for v in top["late_rate_pct"]])
    ax.axvline(overall_late_pct, color=TEXT_2, linewidth=1)
    ax.annotate(
        f"в среднем по стране {overall_late_pct:.1f}%",
        (overall_late_pct, len(top) - 0.4),
        xytext=(4, 0),
        textcoords="offset points",
        fontsize=8,
        color=TEXT_2,
        va="bottom",
    )
    ax.set_title("Штаты с наибольшей долей опозданий")
    ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_xlim(0, top["late_rate_pct"].max() * 1.25)
    ax.set_ylim(-0.6, len(top) + 0.3)
    _value_grid(ax, "x")


DELAY_LABELS = {
    "on_time": "в срок",
    "late_1_3d": "1–3 дня",
    "late_4_7d": "4–7 дней",
    "late_8d_plus": "8+ дней",
}


def plot_review_by_delay(ax, review_by_delay: pd.DataFrame) -> None:
    labels = [DELAY_LABELS[b] for b in review_by_delay["delay_bucket"]]
    colors = [BLUE if b == "on_time" else ORANGE for b in review_by_delay["delay_bucket"]]
    bars = ax.bar(labels, review_by_delay["avg_review_score"], width=0.6, color=colors)
    for bar, score, neg in zip(bars, review_by_delay["avg_review_score"], review_by_delay["negative_review_pct"]):
        cx = bar.get_x() + bar.get_width() / 2
        ax.annotate(
            f"{score:.2f}",
            (cx, bar.get_height()),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=10,
            fontweight="semibold",
            color=TEXT,
        )
        ax.annotate(f"{neg:.0f}%\nоценок 1–2", (cx, 0.15), ha="center", fontsize=8, color="white")
    ax.set_title("Средняя оценка отзыва vs опоздание")
    ax.set_ylim(0, 5.4)
    ax.set_yticks(range(0, 6))
    ax.set_xlabel("доставлено позже обещанной даты на …")
    _value_grid(ax, "y")


def plot_rfm_segments(ax, seg: pd.DataFrame) -> None:
    s = seg.iloc[::-1]
    y = np.arange(len(s))
    h = 0.36
    b1 = ax.barh(y + h / 2, s["customer_share_pct"], height=h, color=BLUE, label="доля клиентов")
    b2 = ax.barh(y - h / 2, s["revenue_share_pct"], height=h, color=ORANGE, label="доля выручки")
    _bar_labels(ax, b1, [f"{v:.0f}%" for v in s["customer_share_pct"]])
    _bar_labels(ax, b2, [f"{v:.0f}%" for v in s["revenue_share_pct"]])
    ax.set_yticks(y, s["segment"])
    ax.set_title("RFM-сегменты: клиенты vs выручка")
    ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_xlim(0, max(s["customer_share_pct"].max(), s["revenue_share_pct"].max()) * 1.2)
    ax.legend(loc="upper right")
    _value_grid(ax, "x")


def plot_retention_heatmap(ax, pivot: pd.DataFrame, sizes: pd.Series) -> None:
    data = pivot.to_numpy(dtype=float)
    vmax = np.nanmax(data)
    im = ax.imshow(data, cmap=BLUE_RAMP, vmin=0, vmax=vmax, aspect="auto")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if v > vmax * 0.55 else TEXT)
    ax.set_xticks(range(data.shape[1]), [f"M{c}" for c in pivot.columns])
    ax.set_yticks(range(data.shape[0]), [f"{c}  ({sizes[c]:,})" for c in pivot.index])
    ax.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title("Когортный retention: % клиентов когорты, купивших снова через N месяцев")
    ax.set_ylabel("когорта первой покупки (размер)")
    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.02, format=PercentFormatter(decimals=1))
    cbar.outline.set_visible(False)


def plot_delivery_distribution(ax, orders: pd.DataFrame) -> None:
    days = orders["delivery_days"].dropna()
    ax.hist(days.clip(0, 60), bins=60, color=BLUE, edgecolor=SURFACE, linewidth=0.5)
    med = days.median()
    ax.axvline(med, color=TEXT_2, linewidth=1)
    ax.annotate(f"медиана {med:.1f} дн.", (med, ax.get_ylim()[1] * 0.92), xytext=(4, 0),
                textcoords="offset points", fontsize=9, color=TEXT_2)
    ax.set_title("Срок доставки, дней (хвост обрезан на 60)")
    ax.set_xlabel("дней от покупки до доставки")
    ax.set_ylabel("заказов")
    _value_grid(ax, "y")


def plot_price_distribution(ax, delivered: pd.DataFrame, iqr_upper: float) -> None:
    prices = delivered["price"]
    bins = np.logspace(np.log10(max(prices.min(), 1)), np.log10(prices.max()), 60)
    ax.hist(prices, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=0.5)
    ax.set_xscale("log")
    ax.axvline(iqr_upper, color=ORANGE, linewidth=1.5)
    ax.annotate(f"граница выбросов (IQR)\nR$ {iqr_upper:.0f}", (iqr_upper, ax.get_ylim()[1] * 0.85),
                xytext=(5, 0), textcoords="offset points", fontsize=9, color=TEXT_2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"R$ {v:,.0f}"))
    ax.set_title("Цена товара (логарифмическая шкала)")
    ax.set_ylabel("позиций")
    _value_grid(ax, "y")


# --- dashboard -----------------------------------------------------------------


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _kpi_tile(ax, label: str, value: str, note: str = "") -> None:
    ax.set_axis_off()
    ax.add_patch(
        plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, facecolor="white", edgecolor=GRID, linewidth=1)
    )
    ax.text(0.07, 0.74, label, transform=ax.transAxes, fontsize=10, color=TEXT_2)
    ax.text(0.07, 0.36, value, transform=ax.transAxes, fontsize=21, fontweight="semibold", color=TEXT)
    if note:
        ax.text(0.07, 0.11, note, transform=ax.transAxes, fontsize=8.5, color=MUTED)


def build_dashboard(r: dict, path: Path) -> None:
    """One-page summary. `r` is the dict returned by run_analysis.run()."""
    k = r["kpis"]
    fig = plt.figure(figsize=(17, 11.5))
    gs = fig.add_gridspec(
        3, 6, height_ratios=[0.45, 1.6, 1.6], hspace=0.38, wspace=0.95,
        left=0.05, right=0.98, top=0.895, bottom=0.05,
    )
    tile_gs = gs[0, :].subgridspec(1, 6, wspace=0.08)
    fig.text(0.05, 0.955, "Olist E-commerce: продажи, клиенты и доставка",
             fontsize=20, fontweight="semibold", color=TEXT)
    fig.text(
        0.05, 0.925,
        f"Доставленные заказы, {k['date_min']} — {k['date_max']}  ·  Brazilian E-Commerce Public Dataset by Olist"
        "  ·  GMV = стоимость товаров без доставки",
        fontsize=11, color=TEXT_2,
    )

    tiles = [
        ("GMV", brl(k["gmv"]), f"{_fmt_int(k['items'])} проданных товаров"),
        ("Заказы", _fmt_int(k["orders"]), f"{_fmt_int(k['customers'])} уникальных клиентов"),
        ("Средний чек (AOV)", f"R$ {k['aov']:.0f}", f"медиана цены товара R$ {r['price_stats']['price_median']:.0f}"),
        ("Повторные покупки", f"{k['repeat_purchase_rate_pct']:.1f}%", f"M1 retention ≈ {k['m1_retention_pct']:.2f}%"),
        ("Доставлено с опозданием", f"{k['late_delivery_rate_pct']:.1f}%",
         f"медиана доставки {k['median_delivery_days']:.0f} дн."),
        ("Средняя оценка", f"{k['avg_review_score']:.2f} / 5",
         f"в срок {k['review_on_time']:.2f} · с опозданием {k['review_late']:.2f}"),
    ]
    for i, (label, value, note) in enumerate(tiles):
        _kpi_tile(fig.add_subplot(tile_gs[0, i]), label, value, note)

    plot_monthly_gmv(fig.add_subplot(gs[1, 0:4]), r["monthly"])
    plot_top_categories(fig.add_subplot(gs[1, 4:6]), r["cat"], n=8)
    plot_late_by_state(fig.add_subplot(gs[2, 0:2]), r["late_by_state"], k["late_delivery_rate_pct"], n=8)
    plot_review_by_delay(fig.add_subplot(gs[2, 2:4]), r["review_by_delay"])
    plot_rfm_segments(fig.add_subplot(gs[2, 4:6]), r["seg"])

    fig.savefig(path, dpi=120)
    plt.close(fig)


def save_all_figures(r: dict, fig_dir: Path) -> None:
    set_style()
    fig_dir.mkdir(parents=True, exist_ok=True)

    def single(name: str, draw, figsize=(11, 5.5)) -> None:
        fig, ax = plt.subplots(figsize=figsize)
        draw(ax)
        fig.tight_layout()
        fig.savefig(fig_dir / name, dpi=130)
        plt.close(fig)

    single("monthly_gmv.png", lambda ax: plot_monthly_gmv(ax, r["monthly"]))
    single("top_categories.png", lambda ax: plot_top_categories(ax, r["cat"]))
    single("top_states.png", lambda ax: plot_top_states(ax, r["region"]))
    single("review_by_delay.png", lambda ax: plot_review_by_delay(ax, r["review_by_delay"]), (8, 5))
    single("rfm_segments.png", lambda ax: plot_rfm_segments(ax, r["seg"]), (10, 5))
    single("retention_heatmap.png",
           lambda ax: plot_retention_heatmap(ax, r["retention_pivot"], r["cohort_sizes"]), (10, 8))
    single("price_outliers.png",
           lambda ax: plot_price_distribution(ax, r["delivered"], r["price_stats"]["iqr_upper"]), (10, 5))

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    plot_delivery_distribution(axes[0], r["orders"])
    plot_late_by_state(axes[1], r["late_by_state"], r["kpis"]["late_delivery_rate_pct"])
    fig.tight_layout()
    fig.savefig(fig_dir / "delivery_analysis.png", dpi=130)
    plt.close(fig)

    build_dashboard(r, fig_dir / "dashboard.png")
