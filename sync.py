#!/usr/bin/env python3
import argparse
import csv
import importlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parent
BASELINKER_API_URL = "https://api.baselinker.com/connector.php"
TRUTHY = {"1", "true", "TRUE", "yes", "YES"}


def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_supplier_config(config, name):
    for supplier in config["suppliers"]:
        if supplier["name"] == name:
            return supplier
    raise RuntimeError(f"Unknown supplier: {name}")


def env_required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_config_value(config, key, env_key=None):
    if env_key:
        value = os.environ.get(env_key, "").strip()
        if value:
            return value
    value = config.get(key)
    if value is None or str(value).strip() == "":
        label = env_key or key
        raise RuntimeError(f"Missing required config value: {label}")
    return str(value).strip()


def fetch_bytes(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SupplierStockSync/1.0)",
            "Accept": "application/xml,text/xml,*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return response.read()
    except HTTPError as error:
        print(f"HTTP error while fetching feed: {error.code} {error.reason}", file=sys.stderr)
        print(f"Final URL: {error.url}", file=sys.stderr)
        raise
    except URLError as error:
        print(f"URL error while fetching feed: {error.reason}", file=sys.stderr)
        raise


def parse_int(value, default=0):
    try:
        return int(float((value or "").strip().replace(",", ".")))
    except (TypeError, ValueError):
        return default


def normalize_stock(row):
    availability = str(row.get("availability", "")).strip()
    if availability == "0":
        return 0
    return parse_int(row.get("stock", ""))


def write_csv(rows, path):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "supplier",
        "supplier_product_id",
        "sku",
        "stock",
        "availability",
        "ean",
        "name",
        "description",
        "category",
        "attributes",
        "url",
        "price",
        "purchase_price",
        "weight",
        "vat",
        "raw_stock",
        "baselinker_product_id",
        "sync_status",
    ]
    extra = []
    seen = set(fieldnames)
    for row in rows:
        for key in row:
            if key not in seen:
                extra.append(key)
                seen.add(key)

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + extra)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def baselinker_request(method, parameters, token):
    data = urllib.parse.urlencode({
        "method": method,
        "parameters": json.dumps(parameters, ensure_ascii=False),
    }).encode("utf-8")
    req = urllib.request.Request(
        BASELINKER_API_URL,
        data=data,
        headers={
            "X-BLToken": token,
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "SupplierStockSync/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("status") != "SUCCESS":
        code = result.get("error_code", "UNKNOWN")
        message = result.get("error_message", "Unknown BaseLinker API error")
        raise RuntimeError(f"BaseLinker {method} failed: {code}: {message}")
    return result


def load_baselinker_products(token, inventory_id):
    products_by_sku = {}
    page = 1
    while True:
        result = baselinker_request(
            "getInventoryProductsList",
            {
                "inventory_id": inventory_id,
                "page": page,
                "include_variants": True,
            },
            token,
        )
        products = result.get("products") or {}
        if not products:
            break
        for product_id, product in products.items():
            sku = str(product.get("sku", "")).strip()
            if sku:
                products_by_sku[sku] = str(product_id)
            variants = product.get("variants") or {}
            if isinstance(variants, dict):
                for variant_id, variant in variants.items():
                    variant_sku = str(variant.get("sku", "")).strip()
                    if variant_sku:
                        products_by_sku[variant_sku] = str(variant_id)
            elif isinstance(variants, list):
                for variant in variants:
                    variant_sku = str(variant.get("sku", "")).strip()
                    variant_id = variant.get("variant_id") or variant.get("id")
                    if variant_sku and variant_id:
                        products_by_sku[variant_sku] = str(variant_id)
        if len(products) < 1000:
            break
        page += 1
    return products_by_sku


def sync_baselinker(rows, supplier_config, dry_run):
    token = env_required(supplier_config.get("baselinker_token_env", "BASELINKER_TOKEN"))
    inventory_id = get_config_value(supplier_config, "baselinker_inventory_id", supplier_config.get("baselinker_inventory_env"))
    warehouse_id = get_config_value(supplier_config, "baselinker_warehouse_id", supplier_config.get("baselinker_warehouse_env"))
    batch_size = int(supplier_config.get("baselinker_batch_size", 1000))

    products_by_sku = load_baselinker_products(token, inventory_id)
    print(f"{supplier_config['name']}: loaded {len(products_by_sku)} BaseLinker products by SKU")

    updates = {}
    matched = 0
    skipped = 0
    for row in rows:
        sku = str(row.get("sku", "")).strip()
        product_id = products_by_sku.get(sku)
        if not sku or not product_id:
            row["sync_status"] = "skipped_no_sku_match"
            skipped += 1
            continue
        if str(row.get("stock", "")).strip() == "" and str(row.get("availability", "")).strip() != "0":
            row["sync_status"] = "skipped_no_stock"
            skipped += 1
            continue
        row["baselinker_product_id"] = product_id
        row["sync_status"] = "dry_run" if dry_run else "pending"
        updates[product_id] = {warehouse_id: normalize_stock(row)}
        matched += 1

    if dry_run:
        print(f"{supplier_config['name']}: DRY RUN matched={matched}, skipped={skipped}")
        return

    updated = 0
    warnings = {}
    items = list(updates.items())
    for offset in range(0, len(items), batch_size):
        batch = dict(items[offset:offset + batch_size])
        result = baselinker_request(
            "updateInventoryProductsStock",
            {
                "inventory_id": inventory_id,
                "products": batch,
            },
            token,
        )
        updated += int(result.get("counter") or 0)
        batch_warnings = result.get("warnings")
        if isinstance(batch_warnings, dict):
            warnings.update(batch_warnings)

    for row in rows:
        if row.get("sync_status") == "pending":
            row["sync_status"] = "updated"

    print(f"{supplier_config['name']}: BaseLinker stock sync OK updated={updated}, skipped={skipped}")
    if warnings:
        print(f"{supplier_config['name']}: BaseLinker warnings: {json.dumps(warnings, ensure_ascii=False)}", file=sys.stderr)


def run_supplier(config, supplier_name, dry_run):
    supplier_config = get_supplier_config(config, supplier_name)
    feed_url = env_required(supplier_config["feed_env"])
    parser = importlib.import_module(f"suppliers.{supplier_config['parser']}")

    xml_bytes = fetch_bytes(feed_url)
    rows = parser.parse(xml_bytes, supplier_config)
    print(f"{supplier_name}: parsed {len(rows)} feed rows")

    sync_baselinker(rows, supplier_config, dry_run)
    csv_path = write_csv(rows, supplier_config["csv_path"])
    print(f"{supplier_name}: wrote diagnostic CSV -> {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Sync supplier XML stock to BaseLinker.")
    parser.add_argument("--config", default=str(ROOT / "config" / "suppliers.json"))
    parser.add_argument("--supplier", required=True)
    parser.add_argument("--dry-run", action="store_true", default=os.environ.get("DRY_RUN", "") in TRUTHY)
    args = parser.parse_args()

    config = load_config(args.config)
    run_supplier(config, args.supplier, args.dry_run)


if __name__ == "__main__":
    main()
