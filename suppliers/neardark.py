import csv
import io


def _first(row, fields):
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _build_sku(value, prefix, separator):
    value = (value or "").strip()
    if not value:
        return ""
    if prefix and value.upper().startswith(prefix.upper()):
        return value
    return f"{prefix}{separator}{value}" if prefix else value


def parse(feed_bytes, config):
    text = feed_bytes.decode(config.get("encoding", "utf-8-sig"), errors="replace")
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    sku_fields = config.get("source_sku_fields", ["SKU", "sku", "Articlenumber", "Article number", "id"])
    stock_fields = config.get("source_stock_fields", ["stock", "Stock", "quantity", "Quantity"])
    image_fields = config.get("source_image_fields", [])
    prefix = config.get("supplier_prefix", "ND")
    separator = config.get("supplier_prefix_sep", "-")

    rows = []
    for source_row in reader:
        source_sku = _first(source_row, sku_fields)
        row = {
            "supplier": config["name"],
            "supplier_product_id": source_sku,
            "sku": _build_sku(source_sku, prefix, separator),
            "stock": _first(source_row, stock_fields),
            "availability": _first(source_row, config.get("source_availability_fields", ["availability", "Availability"])),
            "ean": _first(source_row, config.get("source_ean_fields", ["EAN", "ean", "Barcode", "barcode"])),
            "name": _first(source_row, config.get("source_name_fields", ["Articl name", "Article name", "name"])),
            "description": _first(source_row, config.get("source_description_fields", ["description", "Description"])),
            "url": _first(source_row, config.get("source_url_fields", ["url", "URL"])),
            "purchase_price": _first(source_row, config.get("source_purchase_price_fields", ["price", "Price"])),
            "weight": _first(source_row, config.get("source_weight_fields", ["weight", "Weight"])),
            "raw_stock": _first(source_row, stock_fields),
        }
        for index, field in enumerate(image_fields, start=1):
            image = source_row.get(field)
            if image:
                row[f"image_{index}"] = image.strip()
        rows.append(row)
    return rows
