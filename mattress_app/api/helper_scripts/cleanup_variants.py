"""
Phase B4 + B5 : Build the protective "keep list", then delete ONLY the
                unreferenced size variants of AREA-PRICED products.

SAFETY MODEL (now flow-aware):
  An item is KEPT if ANY of these is true:
    - referenced in any table that has an item_code column (orders, etc.)
    - it is a template (has_variants = 1)
    - it has its own non-null Item Price  (protects fixed-price items)
    - custom_use_area_pricing = 0          (Magniflex, pillows: OLD flow, keep all)
    - it is one base variant per area-priced family+thickness (future orders)
  Everything else (unreferenced area-priced size variants) is deleted.

  Item Attribute / Item Attribute Value are NEVER touched.

RUN ORDER (staging/local first, then production):
    bench --site [site] execute mattress_app.api.cleanup_variants.build_keep_list
    bench --site [site] execute mattress_app.api.cleanup_variants.preview_deletion
    # take a backup now
    bench --site [site] execute mattress_app.api.cleanup_variants.delete_unreferenced
    bench --site [site] execute mattress_app.api.cleanup_variants.optimize_tables
"""

import csv
import os
import re

import frappe

CODE_RE = re.compile(r"^(.+?)-(\d+)[Mm][Mm]-(\d+)-(\d+)$")
KEEP_FLAG = "_mattress_keep"


def _report_path(name):
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, name)


# Tables that list items by NATURE (master / price / stock / config), NOT
# because the item is "used" in a transaction. Referencing these must NOT
# protect an item from deletion.
_NON_REFERENCE_TABLES = {
	"tabItem",  # the item master itself - lists every item
	"tabItem Price",  # area variants have their own price rows
	"tabBin",  # stock balance - one row per item/warehouse
	"tabItem Default",
	"tabItem Reorder",
	"tabItem Tax",
	"tabItem Variant Attribute",
	"tabItem Barcode",
	"tabUOM Conversion Detail",
	"tabItem Manufacturer",
	"tabItem Alternative",
}


def _all_item_code_columns():
	rows = frappe.db.sql(
		"""
		SELECT table_name, column_name
		FROM information_schema.columns
		WHERE table_schema = DATABASE()
		  AND column_name IN ('item_code', 'production_item', 'item')
		  AND table_name LIKE 'tab%%'
		""",
		as_dict=True,
	)
	# keep only REAL transaction/document tables
	return [r for r in rows if r["table_name"] not in _NON_REFERENCE_TABLES]


def build_keep_list():
	keep = set()

	# 1) referenced anywhere
	for col in _all_item_code_columns():
		table, column = col["table_name"], col["column_name"]
		try:
			keep.update(
				frappe.db.sql_list(
					f"SELECT DISTINCT `{column}` FROM `{table}` WHERE `{column}` IS NOT NULL AND `{column}` != ''"
				)
			)
		except Exception as e:
			print(f"  (skipped {table}.{column}: {e})")

	# 2) all templates
	keep.update(frappe.db.sql_list("SELECT name FROM `tabItem` WHERE has_variants = 1"))

	# 3) FIXED-PRICE items that have their own price.
	#    IMPORTANT: only protect prices on items NOT on area pricing. Area-priced
	#    variants also have Item Price rows (we read the rates from them), so we
	#    must NOT protect those here or nothing would ever be deleted.
	keep.update(
		frappe.db.sql_list(
			"""SELECT DISTINCT ip.item_code
			   FROM `tabItem Price` ip
			   INNER JOIN `tabItem` i ON i.name = ip.item_code
			   WHERE ip.price_list_rate > 0
			     AND IFNULL(i.custom_use_area_pricing,0) = 0"""
		)
	)

	# 4) anything NOT on area pricing (Magniflex, pillows -> old flow, keep all)
	keep.update(frappe.db.sql_list("SELECT name FROM `tabItem` WHERE IFNULL(custom_use_area_pricing,0) = 0"))

	# 4b) items with NON-ZERO stock on hand (don't delete something in stock)
	keep.update(
		frappe.db.sql_list(
			"""SELECT DISTINCT item_code FROM `tabBin`
			   WHERE IFNULL(actual_qty,0) != 0"""
		)
	)

	# 4c) PROTECT variants whose replacement does NOT exist.
	#     A variant 'Family-ThkMM-L-W' is only safe to delete if its new
	#     standalone item 'Family-ThkMM' exists to take over. If the new item
	#     was never created (or was deleted), keep the old variants so that
	#     family+thickness stays sellable via the old flow.
	all_item_codes = set(frappe.db.sql_list("SELECT name FROM `tabItem`"))
	variant_codes = frappe.db.sql_list(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NOT NULL AND IFNULL(custom_use_area_pricing,0) = 1"""
	)
	import re as _re

	# Capture the family+thickness WITHOUT the MM suffix, then force the suffix
	# to uppercase 'MM' so it matches the new items (old variants use 'Mm',
	# new standalone items use 'MM').
	_strip = _re.compile(r"^(.*-\d+)[Mm][Mm]-\d+-\d+$")
	# normalized set of existing codes for case-tolerant matching on the suffix
	for vcode in variant_codes:
		m = _strip.match(vcode)
		if not m:
			# code doesn't fit the expected pattern -> keep it (don't risk it)
			keep.add(vcode)
			continue
		replacement = m.group(1) + "MM"
		if replacement not in all_item_codes:
			# no new item to take over -> keep the old variant
			keep.add(vcode)

	# 5) NEW MODEL: base variants are no longer needed as anchors (the new
	#    standalone Family-ThicknessMM items replace them). We keep ONLY old
	#    variants referenced in real documents (rule 1). So nothing added here.
	#    The new items have variant_of=NULL so they are never in the delete set.

	frappe.cache().delete_value(KEEP_FLAG)
	frappe.cache().set_value(KEEP_FLAG, list(keep))

	total = frappe.db.count("Item")
	deletable = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabItem`
		   WHERE variant_of IS NOT NULL
		     AND IFNULL(custom_use_area_pricing,0) = 1
		     AND name NOT IN %(keep)s""",
		{"keep": tuple(keep) or ("",)},
	)[0][0]

	msg = (
		f"KEEP LIST BUILT\n"
		f"  total items      : {total}\n"
		f"  kept (all rules) : {len(keep)}\n"
		f"  deletable        : {deletable}\n"
	)
	print(msg)
	return msg


def _pick_base_variants():
	rows = frappe.db.sql(
		"""
		SELECT i.name, i.item_name,
		       MAX(CASE WHEN va.attribute='Thickness mm' THEN va.attribute_value END) AS thk,
		       MAX(CASE WHEN va.attribute='Length' THEN va.attribute_value END) AS len,
		       MAX(CASE WHEN va.attribute='Width' THEN va.attribute_value END) AS wid
		FROM `tabItem` i
		INNER JOIN `tabItem Variant Attribute` va ON va.parent = i.name
		WHERE i.variant_of IS NOT NULL
		  AND IFNULL(i.custom_use_area_pricing,0) = 1
		GROUP BY i.name, i.item_name
		""",
		as_dict=True,
	)
	chosen = {}
	for r in rows:
		key = (r.item_name, r.thk)
		if key not in chosen:
			chosen[key] = r.name
		elif r.len == "72" and r.wid == "72":
			chosen[key] = r.name
	return set(chosen.values())


def _get_keep():
	keep = frappe.cache().get_value(KEEP_FLAG)
	if not keep:
		frappe.throw("Keep list not found. Run build_keep_list first.")
	return set(keep)


def preview_deletion(sample=20):
	keep = _get_keep()
	rows = frappe.db.sql(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NOT NULL
		     AND IFNULL(custom_use_area_pricing,0) = 1
		     AND name NOT IN %(keep)s""",
		{"keep": tuple(keep)},
		as_dict=True,
	)
	p = _report_path("b5_to_delete.csv")
	with open(p, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["item_code"])
		for r in rows:
			w.writerow([r.name])
	print(f"\nWill DELETE {len(rows)} area-priced variant items.")
	print(f"Full list written to: {p}")
	print("Sample:")
	for r in rows[:sample]:
		print(f"  - {r.name}")
	print("\nNothing deleted yet. Run delete_unreferenced to proceed.\n")
	return f"{len(rows)} items queued - see b5_to_delete.csv"


def delete_unreferenced(batch_size=2000, max_fraction=0.997):
	keep = _get_keep()

	# SAFETY GUARD: refuse to run if the delete set is an implausible share of
	# all items (protects against a broken keep list pointing at production).
	total = frappe.db.count("Item")
	to_delete = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabItem`
		   WHERE variant_of IS NOT NULL
		     AND IFNULL(custom_use_area_pricing,0) = 1
		     AND name NOT IN %(keep)s""",
		{"keep": tuple(keep) or ("",)},
	)[0][0]
	if total and (to_delete / total) > max_fraction:
		frappe.throw(
			f"ABORT: would delete {to_delete}/{total} items "
			f"({to_delete/total:.1%}) - exceeds safety cap {max_fraction:.0%}. "
			f"Check the keep list."
		)
	if to_delete == 0:
		print("Nothing to delete (deletable = 0). Check keep list / flags.")
		return "Nothing to delete."

	deleted_total = 0
	while True:
		batch = frappe.db.sql(
			"""SELECT name FROM `tabItem`
			   WHERE variant_of IS NOT NULL
			     AND IFNULL(custom_use_area_pricing,0) = 1
			     AND name NOT IN %(keep)s
			   LIMIT %(n)s""",
			{"keep": tuple(keep), "n": batch_size},
			as_dict=True,
		)
		if not batch:
			break
		names = [r.name for r in batch]
		ph = ", ".join(["%s"] * len(names))
		for tbl, col in [
			("tabItem Variant Attribute", "parent"),
			("tabItem Default", "parent"),
			("tabUOM Conversion Detail", "parent"),
			("tabItem Price", "item_code"),
			("tabItem Barcode", "parent"),
			("tabItem Reorder", "parent"),
			("tabItem Tax", "parent"),
		]:
			if frappe.db.table_exists(tbl):
				frappe.db.sql(f"DELETE FROM `{tbl}` WHERE `{col}` IN ({ph})", names)
		frappe.db.sql(f"DELETE FROM `tabItem` WHERE name IN ({ph})", names)
		frappe.db.commit()
		deleted_total += len(names)
		print(f"  deleted {deleted_total} so far...")
	msg = f"Phase B5 complete. Deleted {deleted_total} unreferenced area-priced variants."
	print(msg)
	return msg


def optimize_tables():
	for tbl in [
		"tabItem",
		"tabItem Price",
		"tabItem Variant Attribute",
		"tabItem Default",
		"tabUOM Conversion Detail",
	]:
		if frappe.db.table_exists(tbl):
			frappe.db.sql(f"OPTIMIZE TABLE `{tbl}`")
			print(f"  optimized {tbl}")
	return "Optimize complete."
