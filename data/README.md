# Data

Raw CSVs are not committed (~120 MB). Source: [Kaggle — Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (CC BY-NC-SA 4.0).

Required files in this folder:

| File | Rows |
| --- | ---: |
| `olist_customers_dataset.csv` | 99 441 |
| `olist_orders_dataset.csv` | 99 441 |
| `olist_order_items_dataset.csv` | 112 650 |
| `olist_order_payments_dataset.csv` | 103 886 |
| `olist_order_reviews_dataset.csv` | 99 224 |
| `olist_products_dataset.csv` | 32 951 |
| `olist_sellers_dataset.csv` | 3 095 |
| `product_category_name_translation.csv` | 71 |
| `olist_geolocation_dataset.csv` | optional, used only by the SQL schema |

## Option 1 — Kaggle CLI

```bash
pip install kaggle   # needs ~/.kaggle/kaggle.json with your API token
kaggle datasets download -d olistbr/brazilian-ecommerce -p data --unzip
```

## Option 2 — manual download

Download the archive from Kaggle, unzip it and copy the CSVs here:

```bash
bash scripts/copy_data.sh ~/Downloads/archive
```
