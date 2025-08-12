# Vaporshop XML → CSV (PL-only, full fields from sample)

Ten projekt konwertuje **tylko katalog PL** i zapisuje **wszystkie pola** widoczne w dostarczonej próbce XML.
Dla pól HTML (description, description_short) zapisuje wersję *HTML* i *oczyszczoną z HTML*.

## Kolumny CSV
- id_product, id_category_default
- url, price, wholesale_price, weight, unity, unit_price_ratio, width, height, depth
- on_sale, online_only, quantity, minimal_quantity, vat, active
- manufacturer, supplier, reference, ean, upc
- name_pl
- description_pl_html, description_pl_text
- description_short_pl_html, description_short_pl_text
- link_rewrite_pl
- meta_description_pl, meta_keywords_pl, meta_title_pl
- available_now_pl, available_later_pl
- category_default_pl
- categories_pl (lista wartości rozdzielona ` | `)
- image_main, images_all (spacja-separowane URL-e)
- features_pl (format `Nazwa: Wartość; ...`)
