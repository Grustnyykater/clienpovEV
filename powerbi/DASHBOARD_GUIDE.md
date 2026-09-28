# Power BI Dashboard Guide — Olist E-Commerce Analytics

## Goal
One interactive dashboard with **3 pages** (not 15). Import cleaned CSVs from `outputs/`.

## Data sources (Get Data → Text/CSV)

| File | Role |
|------|------|
| `outputs/powerbi_orders.csv` | Fact: orders + RFM segment + delivery flags |
| `outputs/powerbi_order_items.csv` | Fact: items / categories |
| `outputs/rfm_segments.csv` | Dim/summary: segment KPIs |
| `outputs/monthly_sales.csv` | Optional pre-agg for overview charts |
| `outputs/category_sales.csv` | Optional pre-agg |
| `outputs/region_sales.csv` | Optional pre-agg |
| `outputs/retention_heatmap.csv` | Retention matrix |

**Relationships (Model view)**
- `powerbi_order_items[order_id]` → `powerbi_orders[order_id]` (many-to-one)
- Optional: create a Calendar table from `order_purchase_timestamp`

## Page 1 — Overview
**KPI cards**
- Revenue = `SUM(powerbi_orders[revenue])`
- Orders = `DISTINCTCOUNT(powerbi_orders[order_id])`
- Customers = `DISTINCTCOUNT(powerbi_orders[customer_unique_id])`
- AOV = `DIVIDE([Revenue], [Orders])`

**Visuals**
- Line chart: Revenue by `year_month`
- Clustered bar: Top states by revenue
- Donut: order share by top categories (from items table)

**Filters (slicers)**
- `year_month`, `customer_state`, `segment`

## Page 2 — Customers
**Visuals**
- Bar: customers by RFM `segment`
- Bar: revenue by RFM `segment`
- Card: Repeat purchase rate  
  `DIVIDE( CALCULATE(DISTINCTCOUNT(customer_unique_id), FILTER(... frequency logic ...)) )`  
  Or import `kpi_summary.csv` and show the ready metric.
- Matrix / heatmap: import `retention_heatmap.csv` as a matrix visual (cohort × period)

## Page 3 — Operations
**Visuals**
- Card: Average delivery days = `AVERAGE(powerbi_orders[delivery_days])`
- Card: Late delivery rate = `AVERAGE( INT(powerbi_orders[is_late]) )` (True=1)
- Bar: late rate by `customer_state`
- Bar: revenue by `category` (from items)
- Optional: map of Brazil by state if you add a shape map

## DAX snippets

```dax
Revenue = SUM(powerbi_orders[revenue])
Orders = DISTINCTCOUNT(powerbi_orders[order_id])
Customers = DISTINCTCOUNT(powerbi_orders[customer_unique_id])
AOV = DIVIDE([Revenue], [Orders])
Late Delivery Rate = AVERAGE(powerbi_orders[is_late] + 0)
Avg Delivery Days = AVERAGE(powerbi_orders[delivery_days])
```

## Design tips for interviews
- Keep one clear story per page.
- Always sync slicers across pages.
- Add a short text box on Overview with 2–3 business insights from `outputs/key_findings.md`.
- Export PDF screenshot of the dashboard for GitHub README.

## File to commit
Save your `.pbix` as `powerbi/olist_ecommerce_dashboard.pbix` after building locally
(Power BI Desktop is Windows/Microsoft Store; on Mac use a Windows VM or Power BI Service upload of CSVs).
