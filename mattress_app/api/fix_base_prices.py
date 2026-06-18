"""
Phase B1a : Apply the corrected 72x72 base prices for the 10 models whose base
            variant was stale (missed the 2026-03-17 11% increase) or needed a
            manual correction.

These prices were provided and verified by the business. Running this updates
the Standard Selling Item Price for each 72x72 base variant, then re-derive the
area rates by running migrate_prices.run afterwards.

    bench --site [site] execute mattress_app.api.fix_base_prices.dry_run
    bench --site [site] execute mattress_app.api.fix_base_prices.run

Report: sites/[site]/private/files/b1a_base_price_fixes.csv
"""

import csv
import os

import frappe

# item_code -> corrected Standard Selling price
CORRECTIONS = {
	"Dr Back Captivate-150MM-72-72": 89658.00,
	"Dr Back Duet-175MM-72-72": 31674.00,
	"Dr Back Duet Luxury-175MM-72-72": 47569.00,
	"Dr Back Natura-175MM-72-72": 60628.00,
	"Dr Back Natura Organic-175MM-72-72": 56410.00,
	"Dr Back Naturalex-175MM-72-72": 72144.00,
	"Dr Back Naturalite-175MM-72-72": 62892.00,
	"Dr Back Naturalite-250MM-72-72": 80141.98,
	"Dr Back Pocket Luxury-175MM-72-72": 64462.00,
	"Dr Back Opulence-150MM-72-72": 96107.13,
}

PRICE_LIST = "Standard Selling"


def _report_path(name):
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, name)


def _process(write):
	report = []
	for item_code, new_price in CORRECTIONS.items():
		if not frappe.db.exists("Item", item_code):
			report.append([item_code, "", new_price, "ITEM NOT FOUND"])
			continue

		# find the Standard Selling Item Price row(s) for this item
		rows = frappe.get_all(
			"Item Price",
			filters={"item_code": item_code, "price_list": PRICE_LIST},
			fields=["name", "price_list_rate"],
		)

		if not rows:
			# none exists -> would create one
			if write:
				doc = frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": item_code,
						"price_list": PRICE_LIST,
						"price_list_rate": new_price,
					}
				)
				doc.insert(ignore_permissions=True)
			report.append([item_code, "(none)", new_price, "CREATED" if write else "WOULD CREATE"])
			continue

		if len(rows) > 1:
			# multiple rows: keep the first, note the rest (you already cleaned 250MM)
			report.append([item_code, f"{len(rows)} rows", new_price, "MULTIPLE PRICES - review manually"])

		old = rows[0].price_list_rate
		if abs((old or 0) - new_price) < 0.005:
			report.append([item_code, old, new_price, "already correct"])
			continue

		if write:
			frappe.db.set_value("Item Price", rows[0].name, "price_list_rate", new_price)
		report.append([item_code, old, new_price, "UPDATED" if write else "WOULD UPDATE"])

	if write:
		frappe.db.commit()

	p = _report_path("b1a_base_price_fixes.csv")
	with open(p, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["item_code", "old_price", "new_price", "action"])
		w.writerows(report)

	print(f"\n--- Base price fixes {'(WRITTEN)' if write else '(DRY RUN)'} ---")
	for r in report:
		print(f"  {r[0]}: {r[1]} -> {r[2]}  [{r[3]}]")
	print(f"\nReport: {p}\n")
	return f"{len(report)} base prices processed - see b1a_base_price_fixes.csv"


def dry_run():
	return _process(write=False)


def run():
	return _process(write=True)


def clean_duplicates():
	"""
	Remove duplicate Standard Selling Item Price rows for the corrected items,
	keeping the HIGHER price (matches what was done on production: the lower
	stale MRP entry was deleted).

	    bench --site [site] execute mattress_app.api.fix_base_prices.clean_duplicates
	"""
	removed = []
	for item_code in CORRECTIONS:
		rows = frappe.get_all(
			"Item Price",
			filters={"item_code": item_code, "price_list": PRICE_LIST},
			fields=["name", "price_list_rate"],
			order_by="price_list_rate desc",
		)
		if len(rows) > 1:
			# keep rows[0] (highest), delete the rest
			for extra in rows[1:]:
				frappe.delete_doc("Item Price", extra.name, ignore_permissions=True)
				removed.append([item_code, extra.price_list_rate, "DELETED (kept higher)"])
	frappe.db.commit()
	if removed:
		for r in removed:
			print(f"  removed duplicate: {r[0]} @ Rs{r[1]:,.0f}")
	else:
		print("  no duplicates found")
	return f"Removed {len(removed)} duplicate price rows."
