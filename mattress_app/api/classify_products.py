"""
Phase B1b : Classify every product into its pricing flow and stamp Brand.

For each item it decides:
  - custom_use_area_pricing = 1  if the item (or its template) has area-based
    pricing  (code pattern Family-ThicknessMM-L-W and NOT a Magniflex code)
  - custom_use_area_pricing = 0  otherwise (Magniflex, pillows, accessories)
  - brand = 'Magniflex' for any MAGNIFLEX- coded item (creates the Brand if missing)

Writes a CSV report so you can review every decision.

    bench --site [site] execute mattress_app.api.classify_products.dry_run
    bench --site [site] execute mattress_app.api.classify_products.run

Report: sites/[site]/private/files/b1b_classification.csv
"""

import csv
import os
import re

import frappe

CODE_RE = re.compile(r"^(.+?)-(\d+)[Mm][Mm]-(\d+)-(\d+)$")
MAGNIFLEX_BRAND = "Magniflex"

# Accessories / non-mattress products are ALWAYS fixed-price (checkbox OFF),
# regardless of code pattern. Safety net so an oddly-coded accessory can never
# be auto-flagged as area-priced.
ACCESSORY_KEYWORDS = (
	"PILLOW",
	"PROTECTOR",
	"COMFORTER",
	"COVER",
	"CUSHION",
	"TOPPER",
	"BOLSTER",
	"SOFA",
	"CHHONA",
	"MASAND",
	"MASSAND",
	"BEDSHEET",
	"BED SHEET",
)


def _is_accessory(code, item_name):
	u = ((code or "") + " " + (item_name or "")).upper()
	return any(k in u for k in ACCESSORY_KEYWORDS)


def _is_magniflex(code, item_name):
	c = (code or "").upper()
	n = (item_name or "").upper()
	return c.startswith("MAGNIFLEX-") or n.startswith("MAGNIFLEX") or "MAGNIFLEX" in c


# Item Groups that are NEVER area-priced (mattress area pricing only applies
# to foam products under the "Products" group).
NON_MATTRESS_GROUPS = ("Accessories", "Nos", "Raw Material", "Consumable", "Services")


def _classify(code, item_name, variant_of, has_variants, item_group=None):
	"""Return (use_area_pricing, brand_or_None, reason)."""
	# 1) Item Group is the most reliable signal for accessories / non-mattress
	if item_group in NON_MATTRESS_GROUPS:
		return 0, None, f"item group '{item_group}' - fixed pricing"
	# 2) Magniflex is fixed per-size even though it sits under Products
	if _is_magniflex(code, item_name):
		return 0, MAGNIFLEX_BRAND, "Magniflex - fixed per-size pricing"
	# 3) keyword backstop (in case an accessory was filed under Products)
	if _is_accessory(code, item_name):
		return 0, None, "accessory (keyword) - fixed pricing"
	# 4) area pricing if the code matches the standard pattern...
	if CODE_RE.match(code or ""):
		return 1, None, "area-priced variant (matches Family-ThicknessMM-L-W)"
	# ...or if it's a template whose variants are area-priced
	if has_variants:
		# does ANY variant of this template match the area pattern?
		any_variant = frappe.db.sql(
			"""SELECT name FROM `tabItem`
			   WHERE variant_of=%s AND name REGEXP '-[0-9]+[Mm][Mm]-[0-9]+-[0-9]+$'
			   LIMIT 1""",
			(code,),
		)
		if any_variant:
			return 1, None, "template of area-priced variants"
	return 0, None, "fixed-price item (pillow/accessory/standalone)"


def _report_path(name):
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, name)


def _process(write):
	items = frappe.db.sql(
		"""SELECT name, item_name, variant_of, has_variants, brand, item_group
		   FROM `tabItem`""",
		as_dict=True,
	)
	report = []
	area_on = 0
	area_off = 0
	magniflex = 0

	# make sure the Magniflex brand exists if we'll use it
	if write and not frappe.db.exists("Brand", MAGNIFLEX_BRAND):
		frappe.get_doc({"doctype": "Brand", "brand": MAGNIFLEX_BRAND}).insert(ignore_permissions=True)

	for it in items:
		flag, brand, reason = _classify(it.name, it.item_name, it.variant_of, it.has_variants, it.item_group)
		if flag:
			area_on += 1
		else:
			area_off += 1
		if brand == MAGNIFLEX_BRAND:
			magniflex += 1

		report.append([it.name, it.item_name, flag, brand or it.brand or "", reason])

		if write:
			updates = {"custom_use_area_pricing": flag}
			if brand and it.brand != brand:
				updates["brand"] = brand
			frappe.db.set_value("Item", it.name, updates, update_modified=False)

	if write:
		frappe.db.commit()

	p = _report_path("b1b_classification.csv")
	with open(p, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["item_code", "item_name", "use_area_pricing", "brand", "reason"])
		w.writerows(report)

	print(f"\n--- Classification {'(WRITTEN)' if write else '(DRY RUN)'} ---")
	print(f"Total items          : {len(items)}")
	print(f"Area pricing ON      : {area_on}")
	print(f"Area pricing OFF     : {area_off}")
	print(f"Magniflex (brand set): {magniflex}")
	print(f"Report               : {p}\n")
	return f"{area_on} area / {area_off} fixed / {magniflex} magniflex - see b1b_classification.csv"


def dry_run():
	return _process(write=False)


def run():
	return _process(write=True)


def audit_missing_rates():
	"""
	Find products with area-pricing ON but NO rate set for one or more thicknesses.
	These would fail to price at quotation time. Run this after classify + migrate_prices
	to catch misconfigured products in one shot.

	    bench --site [site] execute mattress_app.api.classify_products.audit_missing_rates

	Report: sites/[site]/private/files/b1b_missing_rates.csv
	"""
	# templates flagged for area pricing
	templates = frappe.db.sql(
		"""SELECT DISTINCT IFNULL(i.variant_of, i.name) AS template
		   FROM `tabItem` i
		   WHERE IFNULL(i.custom_use_area_pricing,0) = 1""",
		as_dict=True,
	)

	problems = []
	for t in templates:
		template = t.template
		# thicknesses this template's variants actually use
		thicknesses = frappe.db.sql_list(
			"""SELECT DISTINCT va.attribute_value
			   FROM `tabItem` i
			   INNER JOIN `tabItem Variant Attribute` va ON va.parent = i.name
			   WHERE i.variant_of = %s AND va.attribute = 'Thickness mm'""",
			(template,),
		)
		for thk in thicknesses:
			rate = frappe.db.get_value(
				"Item Thickness Price",
				{"parent": template, "thickness_mm": str(thk)},
				"price_per_sqin",
			)
			if not rate:
				problems.append([template, thk, "area pricing ON but no rate for this thickness"])

	p = _report_path("b1b_missing_rates.csv")
	with open(p, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["template", "thickness_mm", "issue"])
		w.writerows(problems)

	print("\n--- Missing-rate audit ---")
	print(f"Area-priced templates checked : {len(templates)}")
	print(f"Missing rate combinations     : {len(problems)}")
	print(f"Report                        : {p}")
	if problems:
		print("\nFirst few:")
		for row in problems[:10]:
			print(f"  {row[0]} @ {row[1]}MM")
	print("")
	return f"{len(problems)} missing-rate combinations - see b1b_missing_rates.csv"
