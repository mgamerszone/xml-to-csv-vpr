import xml.etree.ElementTree as ET
from collections import defaultdict


def _detect_items(root):
    best = (0, None, None)
    for parent in root.iter():
        counts = {}
        for child in list(parent):
            counts[child.tag] = counts.get(child.tag, 0) + 1
        for tag, count in counts.items():
            if count > best[0]:
                best = (count, parent, tag)
    if best[2] is None:
        return list(root)
    return [child for child in list(best[1]) if child.tag == best[2]]


def _iter_leaves(element, prefix=""):
    for attr, value in element.attrib.items():
        key = f"{prefix}{element.tag}@{attr}"
        if value is not None and str(value).strip():
            yield key, str(value).strip()

    children = list(element)
    text = (element.text or "").strip() if element.text else ""
    if not children:
        if text:
            yield f"{prefix}{element.tag}", text
        return

    for child in children:
        yield from _iter_leaves(child, f"{prefix}{element.tag}_")


def _flatten_item(element):
    bucket = defaultdict(list)
    for key, value in _iter_leaves(element):
        bucket[key].append(value)

    flat = {}
    for key, values in bucket.items():
        seen = set()
        unique = []
        for value in values:
            if value not in seen:
                unique.append(value)
                seen.add(value)
        flat[key] = " | ".join(unique)
    return flat


def _build_sku(value, prefix, separator):
    value = (value or "").strip()
    if not value:
        return ""
    if prefix and value.upper().startswith(prefix.upper()):
        return value
    return f"{prefix}{separator}{value}" if prefix else value


def _pair_attributes(names, values):
    names = [name.strip() for name in (names or "").split(" | ") if name.strip()]
    values = [value.strip() for value in (values or "").split(" | ") if value.strip()]
    pairs = []
    for index, name in enumerate(names):
        value = values[index] if index < len(values) else ""
        pairs.append(f"{name}: {value}".strip(": ").strip())
    return "; ".join(pairs)


def parse(xml_bytes, config):
    root = ET.fromstring(xml_bytes)
    item_tag = config.get("item_tag", "")
    if item_tag:
        items = [element for element in root.iter() if element.tag == item_tag]
        if not items:
            items = _detect_items(root)
    else:
        items = _detect_items(root)

    sku_field = config.get("source_sku_field", "o@id")
    stock_field = config.get("source_stock_field", "o@stock")
    prefix = config.get("supplier_prefix", "KP")
    separator = config.get("supplier_prefix_sep", "-")

    rows = []
    for item in items:
        flat = _flatten_item(item)
        sku = _build_sku(flat.get(sku_field, ""), prefix, separator)
        rows.append({
            "supplier": config["name"],
            "supplier_product_id": flat.get(sku_field, ""),
            "sku": sku,
            "stock": flat.get(stock_field, ""),
            "availability": flat.get(config.get("source_availability_field", "o@avail"), ""),
            "ean": flat.get(config.get("source_ean_field", ""), ""),
            "name": flat.get(config.get("source_name_field", "o_name"), ""),
            "description": flat.get(config.get("source_description_field", "o_desc"), ""),
            "category": flat.get(config.get("source_category_field", "o_cat"), ""),
            "attributes": _pair_attributes(
                flat.get(config.get("source_attribute_name_field", "o_attrs_a@name"), ""),
                flat.get(config.get("source_attribute_value_field", "o_attrs_a"), ""),
            ),
            "url": flat.get(config.get("source_url_field", "o@url"), ""),
            "price": flat.get(config.get("source_price_field", "o@price"), ""),
            "raw_stock": flat.get(stock_field, ""),
        })
    return rows
