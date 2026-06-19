# Supplier stock sync for BaseLinker

This repository synchronizes supplier XML stock feeds into BaseLinker.

Current suppliers:

- `vpr` - Vaporshop feed.
- `konop` - Konopny Sklep feed.
- `neardark` - Neardark CSV feed.

Each supplier can update a different BaseLinker catalog and warehouse. Products are matched by SKU. If supplier products are manually linked in BaseLinker to a main store product, this sync only updates the supplier catalog stock; BaseLinker keeps the manual product relationships.

## Flow

```text
supplier XML feed
-> supplier parser
-> normalized rows: supplier, sku, stock
-> BaseLinker catalog lookup by SKU
-> updateInventoryProductsStock for that supplier catalog and warehouse
-> diagnostic CSV artifact
```

## GitHub Actions secrets

Shared:

- `BASELINKER_TOKEN`

VPR:

- `VPR_FEED_URL`
- `VPR_BASELINKER_INVENTORY_ID`
- `VPR_BASELINKER_WAREHOUSE_ID`

Konop:

- `KONOP_FEED_URL`
- `KONOP_BASELINKER_INVENTORY_ID`
- `KONOP_BASELINKER_WAREHOUSE_ID`

Configured BaseLinker catalogs and warehouses:

| Supplier | Catalog ID | Warehouse ID | SKU prefix |
| --- | ---: | ---: | --- |
| `vpr` | `62748` | `84217` | `VPR-` |
| `konop` | `62750` | `84783` | none |
| `neardark` | `62749` | `84221` | none |

The GitHub Actions workflow runs every 5 minutes. This is the shortest practical schedule for GitHub Actions, but it is not truly real-time. For near-immediate stock updates, run `sync.py` as a persistent service or cron job on a VPS/hosting server every 30-60 seconds, or use supplier webhooks if available.

Manual runs accept:

- `supplier`: `all`, `vpr`, `konop`, or `neardark`
- `dry_run`: `1` to match products and generate CSV without updating BaseLinker stock

## Supplier config

Supplier settings live in `config/suppliers.json`.

Important fields:

- `feed_env` - environment variable containing the supplier XML URL.
- `csv_path` - diagnostic CSV output path.
- `supplier_prefix` and `supplier_prefix_sep` - used when supplier IDs need to become SKUs.
- `baselinker_inventory_env` - environment variable containing the BaseLinker catalog ID for this supplier.
- `baselinker_warehouse_env` - environment variable containing the BaseLinker warehouse ID for this supplier.

Default SKU behavior:

- VPR: feed `reference` becomes SKU, with `VPR-` prefix if missing.
- Konop: feed `o@id` becomes SKU without a prefix.
- Neardark: `Order No.` becomes SKU without a prefix.

Adjust `supplier_prefix` if BaseLinker uses a different SKU convention. If Neardark is reimported with prefixed SKUs later, set `supplier_prefix` to `ND` and `supplier_prefix_sep` to `-`.

Stock availability rule:

- If a supplier feed exposes availability as `0`, synchronized stock is forced to `0`, even when the stock field contains a positive value.

Currently synced to BaseLinker:

- stock only, via `updateInventoryProductsStock`.

Captured in diagnostic CSV for future product-data mapping:

- Konop: retail price, description, category, attributes, availability.
- VPR: net retail price, purchase price, weight, VAT, EAN, additional EAN, PL descriptions, category, images, attributes.
- Neardark: EUR purchase price, EN name, EN description.

Neardark note: the currently provided `Product_EN.csv` feed does not expose stock. The sync therefore skips Neardark stock updates with `skipped_no_stock` until a stock column or a separate stock feed is available.

Product data and price updates should be enabled only after confirming exact BaseLinker price group IDs, text field keys, category strategy, and attribute field mapping. This avoids overwriting manually curated catalog data.

## Local usage

Dry run for VPR:

```bash
VPR_FEED_URL="https://example.com/vpr.xml" \
BASELINKER_TOKEN="..." \
VPR_BASELINKER_INVENTORY_ID="..." \
VPR_BASELINKER_WAREHOUSE_ID="..." \
python sync.py --supplier vpr --dry-run
```

Dry run for Konop:

```bash
KONOP_FEED_URL="https://example.com/konop.xml" \
BASELINKER_TOKEN="..." \
KONOP_BASELINKER_INVENTORY_ID="..." \
KONOP_BASELINKER_WAREHOUSE_ID="..." \
python sync.py --supplier konop --dry-run
```

Dry run for Neardark:

```bash
NEARDARK_FEED_URL="https://example.com/neardark.csv" \
BASELINKER_TOKEN="..." \
python sync.py --supplier neardark --dry-run
```

Remove `--dry-run` to update stock.

## Diagnostic CSV

Each run writes a CSV artifact with normalized data and sync status:

- `data/vpr.csv`
- `data/konop.csv`
- `data/neardark.csv`

These files are for inspection and troubleshooting. BaseLinker API is the source of the actual stock update.
