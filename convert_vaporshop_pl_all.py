#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vaporshop XML → CSV (PL-only)
- Czyta feed z FEED_URL (env) i config z config.json
- Normalizuje EAN: ciągi z samych zer → puste pole
- Dodaje prefiks dostawcy do reference (SKU): domyślnie "VPR-<reference>"
- Rozdziela zdjęcia na kolumny image_1..image_N (N z configu: max_images)
- Usuwa HTML z description_short (zostawia też wersję HTML)
- Tworzy public/feed.csv oraz prosty public/index.html
Stdlib only.
"""

import os, sys, csv, json, html, re, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def strip_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s, flags=re.S|re.I)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def text(node):
    return (node.text or "").strip() if node is not None else ""

def lang_value(parent, lang_code="pl"):
    """Zwraca tekst z <value xml:lang="...">; jeśli brak danego języka, bierze pierwszy <value>."""
    if parent is None:
        return ""
    chosen = None
    for v in parent.findall("./value"):
        if v.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") == lang_code:
            chosen = v
            break
        if chosen is None:
            chosen = v
    return (chosen.text or "").strip() if chosen is not None else ""

def collect_categories(cat_parent, lang_code="pl"):
    if cat_parent is None:
        return []
    out = []
    for cat in cat_parent.findall("./category"):
        out.append(lang_value(cat, lang_code))
    return [c for c in out if c]

def collect_images(imgs_parent):
    main = ""
    all_imgs = []
    if imgs_parent is None:
        return main, all_imgs
    main_node = imgs_parent.find("./main")
    if main_node is not None and "url" in main_node.attrib:
        main = main_node.attrib["url"].strip()
        all_imgs.append(main)
    for i in imgs_parent.findall("./i"):
        u = i.attrib.get("url", "").strip()
        if u:
            all_imgs.append(u)
    # de-dupe keeping order
    seen = set(); uniq = []
    for u in all_imgs:
        if u not in seen:
            uniq.append(u); seen.add(u)
    return main, uniq

def collect_features(feats_parent, lang_code="pl"):
    if feats_parent is None:
        return ""
    parts = []
    for f in feats_parent.findall("./feature"):
        name_parent = f.find("./name")
        val_parent = f.find("./value")
        n = lang_value(name_parent, lang_code)
        v = lang_value(val_parent, lang_code)
        if n or v:
            parts.append(f"{n}: {v}".strip(": ").strip())
    return "; ".join([p for p in parts if p])

def fetch_xml(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (XML->CSV bot; +https://example.com)"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()

def normalize_ean(e: str) -> str:
    """Puste dla '0', '00', '000'...; w innym przypadku zwraca obcięty EAN."""
    s = (e or "").strip()
    return "" if re.fullmatch(r"0+", s) else s

def apply_supplier_prefix(ref: str, prefix: str, sep: str) -> str:
    """
    Dodaje prefiks dostawcy do reference.
    - Nie dubluje, jeśli już zaczyna się od prefiksu (ignoruje wielkość liter i '-', '_' lub spację po prefiksie).
    - Jeśli reference puste → zostawia puste.
    """
    r = (ref or "").strip()
    if not r:
        return ""
    pattern = r"^(?:" + re.escape(prefix) + r")(?:[-_ ]|$)"
    if re.match(pattern, r, flags=re.I):
        return r
    # pozwól wyłączyć separator podając "" w configu
    sep = sep if sep is not None else ""
    return f"{prefix}{sep}{r}"

def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    feed_url = os.environ.get("FEED_URL")
    if not feed_url:
        print("ERROR: Missing FEED_URL", file=sys.stderr)
        sys.exit(1)

    raw = fetch_xml(feed_url)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"XML parse error: {e}", file=sys.stderr)
        sys.exit(1)

    lang = cfg.get("lang", "pl")
    max_images = int(cfg.get("max_images", 10))
    supplier_prefix = cfg.get("supplier_prefix", "VPR")
    supplier_prefix_sep = cfg.get("supplier_prefix_sep", "-")

    out_dir = ROOT / "public"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "feed.csv"

    delim = cfg.get("csv_delimiter", ",")
    quotechar = cfg.get("csv_quotechar", '"')
    encoding = cfg.get("encoding", "utf-8")

    products = root.findall(".//product")

    # Nagłówki
    headers = [
        "id_product","id_category_default","url","price","wholesale_price","weight","unity",
        "unit_price_ratio","width","height","depth","on_sale","online_only","quantity",
        "minimal_quantity","vat","active","manufacturer","supplier","reference","ean","upc",
        "name_pl",
        "description_pl_html","description_pl_text",
        "description_short_pl_html","description_short_pl_text",
        "link_rewrite_pl",
        "meta_description_pl","meta_keywords_pl","meta_title_pl",
        "available_now_pl","available_later_pl",
        "category_default_pl","categories_pl",
        "image_main"
    ] + [f"image_{i}" for i in range(1, max_images+1)] + [
        "features_pl"
    ]

    rows = []
    for p in products:
        id_product = text(p.find("./id_product"))
        id_category_default = text(p.find("./id_category_default"))
        url = text(p.find("./url"))
        price = text(p.find("./price"))
        wholesale_price = text(p.find("./wholesale_price"))
        weight = text(p.find("./weight"))
        unity = text(p.find("./unity"))
        unit_price_ratio = text(p.find("./unit_price_ratio"))
        width = text(p.find("./width"))
        height = text(p.find("./height"))
        depth = text(p.find("./depth"))
        on_sale = text(p.find("./on_sale"))
        online_only = text(p.find("./online_only"))
        quantity = text(p.find("./quantity"))
        minimal_quantity = text(p.find("./minimal_quantity"))
        vat = text(p.find("./vat"))
        active = text(p.find("./active"))
        manufacturer = text(p.find("./manufacturer"))
        supplier = text(p.find("./supplier"))

        reference_raw = text(p.find("./reference"))
        reference = apply_supplier_prefix(reference_raw, supplier_prefix, supplier_prefix_sep)

        ean = normalize_ean(text(p.find("./ean")))
        upc = text(p.find("./upc"))

        name_pl = lang_value(p.find("./name"), lang)
        desc_pl_html = lang_value(p.find("./description"), lang)
        desc_pl_text = strip_html(desc_pl_html)
        descs_pl_html = lang_value(p.find("./description_short"), lang)
        descs_pl_text = strip_html(descs_pl_html)
        link_rewrite_pl = lang_value(p.find("./link_rewrite"), lang)
        meta_description_pl = lang_value(p.find("./meta_description"), lang)
        meta_keywords_pl = lang_value(p.find("./meta_keywords"), lang)
        meta_title_pl = lang_value(p.find("./meta_title"), lang)
        available_now_pl = lang_value(p.find("./available_now"), lang)
        available_later_pl = lang_value(p.find("./available_later"), lang)

        cat_default_pl = lang_value(p.find("./category_default"), lang)
        cats_pl = collect_categories(p.find("./categories"), lang)
        cats_pl_str = " | ".join([c for c in cats_pl if c])

        image_main, images_all = collect_images(p.find("./imgs"))
        img_cols = [images_all[i] if i < len(images_all) else "" for i in range(max_images)]

        features_pl = collect_features(p.find("./features"), lang)

        rows.append([
            id_product,id_category_default,url,price,wholesale_price,weight,unity,
            unit_price_ratio,width,height,depth,on_sale,online_only,quantity,
            minimal_quantity,vat,active,manufacturer,supplier,reference,ean,upc,
            name_pl,
            desc_pl_html,desc_pl_text,
            descs_pl_html,descs_pl_text,
            link_rewrite_pl,
            meta_description_pl,meta_keywords_pl,meta_title_pl,
            available_now_pl,available_later_pl,
            cat_default_pl,cats_pl_str,
            image_main, *img_cols, features_pl
        ])

    with out_csv.open("w", newline="", encoding=encoding) as f:
        w = csv.writer(f, delimiter=delim, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL)
        w.writerow(headers)
        w.writerows(rows)

    # Prosty index dla wygody
    (out_dir / "index.html").write_text('<a href="feed.csv">feed.csv</a>', encoding="utf-8")

    print(f"OK: {len(rows)} rows -> {out_csv}")

if __name__ == "__main__":
    main()
