# Power BI: модель и отчёт

Отчёт `OlistDashboard` хранится в формате **PBIP**: модель описана в TMDL, отчёт — в PBIR. Это текстовые файлы, поэтому изменения мер и визуалов видны в git.

```text
powerbi/
├── OlistDashboard.pbip                  # точка входа: открыть в Power BI Desktop
├── OlistDashboard.SemanticModel/definition/
│   ├── expressions.tmdl                 # параметр DataFolder — путь к outputs/
│   ├── relationships.tmdl
│   └── tables/                          # Orders, OrderItems, Calendar, Retention
└── OlistDashboard.Report/definition/pages/   # 3 страницы, визуалы — по папке на каждый
```

## Как открыть

1. `python scripts/run_analysis.py` — создаёт `outputs/powerbi_orders.csv`, `outputs/powerbi_order_items.csv`, `outputs/retention_heatmap.csv`.
2. `python scripts/configure_powerbi.py` — записывает в параметр `DataFolder` путь к `outputs\` этой копии репозитория.
3. Открыть `OlistDashboard.pbip` в Power BI Desktop и нажать «Обновить».

## Модель

| Таблица | Источник | Гранулярность |
| --- | --- | --- |
| `Orders` | `powerbi_orders.csv` | доставленный заказ: выручка, срок доставки, опоздание, оценка, RFM-сегмент клиента |
| `OrderItems` | `powerbi_order_items.csv` | позиция заказа: категория, цена |
| `Calendar` | вычисляемая (DAX) | день, 2016-09-01 … 2018-08-31 |
| `Retention` | `retention_heatmap.csv` (unpivot в Power Query) | когорта × месяц после первой покупки |

Связи: `OrderItems[order_id]` → `Orders[order_id]`, `Orders[order_date]` → `Calendar[Date]` (многие к одному, фильтр в одну сторону). Поэтому срезы по штату и сегменту действуют и на категории.

Power Query типизирует колонки с культурой `en-US`: в CSV десятичный разделитель — точка, а у Power BI с русской локалью — запятая.

## Меры

| Мера | DAX |
| --- | --- |
| Выручка | `SUM(Orders[revenue])` |
| Заказы | `COUNTROWS(Orders)` |
| Клиенты | `DISTINCTCOUNT(Orders[customer_unique_id])` |
| Средний чек | `DIVIDE([Выручка], [Заказы])` |
| Повторные покупки | доля клиентов с 2+ заказами: `ADDCOLUMNS(VALUES(customer), …)` + `FILTER` |
| Доля опозданий | `AVERAGE(Orders[is_late])` — пустые значения (заказ без даты доставки) не учитываются |
| Доля опозданий (штаты 100+) | `IF([Заказы] >= 100, [Доля опозданий])` — для рейтинга штатов |
| Срок доставки, дн. / Средняя оценка | `AVERAGE` по заказам |
| Негативные отзывы | доля оценок 1–2 среди заказов с отзывом |
| Доля клиентов / Доля выручки | доля сегмента: `DIVIDE(x, CALCULATE(x, REMOVEFILTERS(Orders[RFM-сегмент], …)))` |
| Выручка по позициям / Доля GMV | то же на уровне категорий |
| Вернулись | `AVERAGE(Retention[retention])` |
| Цвет retention | цвет ячейки тепловой карты (условное форматирование матрицы) |

Без фильтров меры совпадают с `outputs/kpi_summary.csv` и SQL-запросами: выручка R$ 13 221 498, 96 478 заказов, 93 358 клиентов, опоздания 6,8%, повторные покупки 3,0%.

## Страницы

- **Обзор** — KPI, выручка по месяцам (2017–2018), топ-12 категорий, топ-10 штатов; срезы по штату и RFM-сегменту.
- **Клиенты** — RFM-сегменты (доля клиентов и выручки), матрица когортного retention M1–M6 с цветовой шкалой.
- **Доставка** — доля опозданий по штатам и месяцам, средняя оценка в зависимости от опоздания.
