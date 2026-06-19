import html
import re
import xml.etree.ElementTree as ET


def _text(node):
    return (node.text or "").strip() if node is not None else ""


def _lang_value(parent, lang_code="pl"):
    if parent is None:
        return ""
    chosen = None
    for value in parent.findall("./value"):
        if value.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == lang_code:
            chosen = value
            break
        if chosen is None:
            chosen = value
    return (chosen.text or "").strip() if chosen is not None else ""


def _strip_html(value):
    value = re.sub(r"<[^>]+>", " ", value or "", flags=re.S | re.I)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_ean(value):
    value = (value or "").strip()
    return "" if re.fullmatch(r"0+", value) else value


def _apply_prefix(value, prefix, separator):
    value = (value or "").strip()
    if not value:
        return ""
    pattern = r"^(?:" + re.escape(prefix) + r")(?:[-_ ]|$)"
    if re.match(pattern, value, flags=re.I):
        return value
    separator = separator if separator is not None else ""
    return f"{prefix}{separator}{value}"


def _collect_images(product, max_images):
    images = []
    imgs_parent = product.find("./imgs")
    if imgs_parent is None:
        return images
    main = imgs_parent.find("./main")
    if main is not None and main.attrib.get("url"):
        images.append(main.attrib["url"].strip())
    for image in imgs_parent.findall("./i"):
        url = image.attrib.get("url", "").strip()
        if url:
            images.append(url)

    unique = []
    seen = set()
    for image in images:
        if image not in seen:
            unique.append(image)
            seen.add(image)
    return unique[:max_images]


def _collect_features(product, lang):
    features_parent = product.find("./features")
    if features_parent is None:
        return ""
    parts = []
    for feature in features_parent.findall("./feature"):
        name = _lang_value(feature.find("./name"), lang)
        value = _lang_value(feature.find("./value"), lang)
        if name or value:
            parts.append(f"{name}: {value}".strip(": ").strip())
    return "; ".join(parts)


def parse(xml_bytes, config):
    root = ET.fromstring(xml_bytes)
    lang = config.get("lang", "pl")
    prefix = config.get("supplier_prefix", "VPR")
    separator = config.get("supplier_prefix_sep", "-")
    max_images = int(config.get("max_images", 10))

    rows = []
    for product in root.findall(".//product"):
        reference = _apply_prefix(_text(product.find("./reference")), prefix, separator)
        stock = _text(product.find("./quantity"))
        images = _collect_images(product, max_images)
        row = {
            "supplier": config["name"],
            "supplier_product_id": _text(product.find("./id_product")),
            "sku": reference,
            "stock": stock,
            "availability": _text(product.find("./active")),
            "ean": _normalize_ean(_text(product.find("./ean"))),
            "additional_ean_1": _text(product.find("./upc")),
            "name": _lang_value(product.find("./name"), lang),
            "description": _strip_html(_lang_value(product.find("./description"), lang)),
            "additional_description_1": _strip_html(_lang_value(product.find("./description_short"), lang)),
            "category": _lang_value(product.find("./category_default"), lang),
            "attributes": _collect_features(product, lang),
            "url": _text(product.find("./url")),
            "price": _text(product.find("./price")),
            "purchase_price": _text(product.find("./wholesale_price")),
            "weight": _text(product.find("./weight")),
            "vat": _text(product.find("./vat")),
            "raw_stock": stock,
        }
        for index, image in enumerate(images, start=1):
            row[f"image_{index}"] = image
        rows.append({
            **row,
        })
    return rows
