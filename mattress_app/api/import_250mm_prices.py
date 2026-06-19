"""
Module 4b : Import new 250MM (or any fixed-thickness) standalone items from an
Excel price list, creating each item + its 72x72 Item Price.

Use this for families whose creation was SKIPPED because their old 72x72 base
variant had price 0. The spreadsheet supplies the correct 72x72 price directly.

Expected sheet columns (header row, case-insensitive):
    Item Code   ->  e.g. "Dr Back Blissline-250MM"  (suffix already included)
    Item Name   ->  e.g. "Dr Back Blissline"        (family only)
    Rate        ->  e.g. 35174                       (the 72x72 price)
    Currency    ->  ignored (assumed INR)

For each row it creates (idempotent):
    Item       : code from sheet, item_name = family, item_group "Products",
                 brand auto-detected, custom_use_area_pricing = 1,
                 custom_thickness_link set, variant_of NULL
    Item Price : Standard Selling, price_list_rate = Rate
    Item Name  : ensure the family record exists (for the custom_name dropdown)

PLACE the xlsx on the bench, then:
    bench --site [site] execute mattress_app.api.import_250mm_prices.dry_run --kwargs "{'path':'/path/to/file.xlsx'}"
    bench --site [site] execute mattress_app.api.import_250mm_prices.run     --kwargs "{'path':'/path/to/file.xlsx'}"
"""

import re

import frappe

PRICE_LIST = "Standard Selling"
DEFAULT_GROUP = "Products"
DEFAULT_UOM = "Nos"
_THK_RE = re.compile(r"-(\d+)MM$", re.IGNORECASE)

# brand prefixes (longest first so multi-word brands match before short ones)
_BRANDS = [
	"Magniflex",
	"Dr. Back",
	"Dr Back",
	"Cherish",
	"V-Rest",
	"V-REST",
	"B'Chhona",
	"MM Foam",
	"Reliance",
]


def _resolve_path(path):
	"""Accept an absolute path, OR just a filename / 'private/files/x.xlsx' and
	resolve it against the site's file directories."""
	import os

	if os.path.isabs(path) and os.path.exists(path):
		return path
	candidates = [
		path,
		frappe.get_site_path(path.lstrip("/")),
		frappe.get_site_path("private", "files", os.path.basename(path)),
		frappe.get_site_path("public", "files", os.path.basename(path)),
	]
	for c in candidates:
		if c and os.path.exists(c):
			return c
	frappe.throw(
		"File not found. Tried:\n"
		+ "\n".join(str(c) for c in candidates)
		+ "\nUpload the xlsx via the ERPNext File manager, then pass its name."
	)


def _read_rows(path):
	import openpyxl

	path = _resolve_path(path)
	wb = openpyxl.load_workbook(path, data_only=True)
	ws = wb.active
	rows = list(ws.iter_rows(values_only=True))
	if not rows:
		return []
	# map header -> index (case-insensitive, trimmed)
	header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]

	def col(name):
		name = name.lower()
		return header.index(name) if name in header else None

	i_code = col("item code")
	i_name = col("item name")
	i_rate = col("rate")
	if i_code is None or i_rate is None:
		frappe.throw("Sheet must have 'Item Code' and 'Rate' columns.")

	out = []
	for r in rows[1:]:
		if r is None:
			continue
		code = r[i_code]
		if not code:
			continue
		code = str(code).strip()
		name = str(r[i_name]).strip() if (i_name is not None and r[i_name]) else None
		rate = r[i_rate]
		try:
			rate = float(rate)
		except (TypeError, ValueError):
			rate = 0
		out.append({"code": code, "name": name, "rate": rate})
	return out


def _hsn_for_family(family, code):
	"""Find a GST HSN code to use for the new item: prefer one already used by
	another item of the same family (old variants are GST-compliant), else any
	mattress item's HSN, else None."""
	# 1) another item with the same family name
	hsn = frappe.db.get_value(
		"Item",
		{"item_name": family, "gst_hsn_code": ["is", "set"]},
		"gst_hsn_code",
	)
	if hsn:
		return hsn
	# 2) an old variant whose code starts with the family
	like = code.split("-")[0] + "%"
	hsn = frappe.db.sql(
		"""SELECT gst_hsn_code FROM `tabItem`
		   WHERE name LIKE %s AND IFNULL(gst_hsn_code,'') != '' LIMIT 1""",
		(like,),
	)
	if hsn:
		return hsn[0][0]
	# 3) any Products item's HSN as a last resort
	hsn = frappe.db.get_value(
		"Item",
		{"item_group": "Products", "gst_hsn_code": ["is", "set"]},
		"gst_hsn_code",
	)
	return hsn


def _detect_brand(code):
	for b in _BRANDS:
		if code.lower().startswith(b.lower()):
			return b
	return None


def _ensure_item_name(family):
	if family and not frappe.db.exists("Item Name", {"item_name": family}):
		frappe.get_doc({"doctype": "Item Name", "item_name": family}).insert(ignore_permissions=True)


def _thickness_name(thk):
	return frappe.db.get_value("Thickness", {"value": str(thk)}, "name")


def _ensure_thickness(thk):
	nm = _thickness_name(thk)
	if nm:
		return nm
	doc = frappe.get_doc({"doctype": "Thickness", "value": str(thk)})
	doc.insert(ignore_permissions=True)
	return doc.name


def _set_item_price(code, rate):
	existing = frappe.get_all(
		"Item Price",
		filters={"item_code": code, "price_list": PRICE_LIST, "selling": 1},
		fields=["name"],
	)
	if existing:
		frappe.db.set_value("Item Price", existing[0].name, "price_list_rate", rate)
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": code,
				"price_list": PRICE_LIST,
				"selling": 1,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)


def dry_run(path):
	rows = _read_rows(path)
	will_create, will_update, bad = [], [], []
	for r in rows:
		if r["rate"] <= 0:
			bad.append(r["code"])
			continue
		if frappe.db.exists("Item", r["code"]):
			will_update.append(r["code"])
		else:
			will_create.append(r["code"])
	print(f"Rows read        : {len(rows)}")
	print(f"Will CREATE items: {len(will_create)}")
	print(f"Will UPDATE price : {len(will_update)} (already exist)")
	print(f"Bad/zero rate     : {len(bad)}")
	if bad:
		print("  zero-rate rows:", ", ".join(bad[:10]))
	print("\nSample to create:")
	for c in will_create[:10]:
		print("  ", c)
	return f"DRY RUN: create {len(will_create)}, update {len(will_update)}, bad {len(bad)}"


def run(path):
	rows = _read_rows(path)
	created, updated, skipped = [], [], []

	for r in rows:
		code, rate = r["code"], r["rate"]
		if rate <= 0:
			skipped.append(code)
			continue

		# derive family + thickness
		m = _THK_RE.search(code)
		thk = m.group(1) if m else None
		family = r["name"] or (code[: m.start()] if m else code)

		if thk:
			_ensure_thickness(thk)
		_ensure_item_name(family)

		if frappe.db.exists("Item", code):
			# refresh price + make sure flags/name are right
			frappe.db.set_value(
				"Item",
				code,
				{
					"item_name": family,
					"custom_use_area_pricing": 1,
				},
				update_modified=False,
			)
			if thk:
				tn = _thickness_name(thk)
				if tn:
					frappe.db.set_value("Item", code, "custom_thickness_link", tn, update_modified=False)
			_set_item_price(code, rate)
			updated.append(code)
			continue

		doc = frappe.new_doc("Item")
		doc.item_code = code
		doc.item_name = family
		doc.item_group = DEFAULT_GROUP
		doc.stock_uom = DEFAULT_UOM
		doc.custom_use_area_pricing = 1
		doc.has_variants = 0
		doc.variant_of = None
		brand = _detect_brand(code)
		if brand and frappe.db.exists("Brand", brand):
			doc.brand = brand
		if thk:
			doc.custom_thickness_link = _thickness_name(thk)
		hsn = _hsn_for_family(family, code)
		if hsn:
			doc.gst_hsn_code = hsn
		doc.insert(ignore_permissions=True)
		_set_item_price(code, rate)
		created.append(code)

	frappe.db.commit()
	msg = (
		f"Import done. Created {len(created)}, updated {len(updated)}, " f"skipped(zero rate) {len(skipped)}."
	)
	print(msg)
	if skipped:
		print("Skipped:", ", ".join(skipped[:10]))
	return msg
