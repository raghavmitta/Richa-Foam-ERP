"""
Module 3 : Assign brand to EXISTING products by name/code prefix.

Detection rules (existing products only):
    MAGNIFLEX...        -> Magniflex
    DR.BACK / DR BACK   -> Dr. Back
    CHERISH             -> Cherish
    V-REST / VREST      -> V-Rest
    CHHONA / B'CH       -> B'Chhona
    MM FOAM             -> MM Foam   (rare in current data)
    RELIANCE            -> Reliance  (rare in current data)

Left BLANK on purpose (you will brand these later):
    Bonded seat, Feather Rest, and any MM Foam / Reliance products not
    detectable by name yet.

Creates any missing Brand master records. Writes a CSV of every change.

    bench --site [site] execute mattress_app.api.assign_brands.dry_run
    bench --site [site] execute mattress_app.api.assign_brands.run

Report: sites/[site]/private/files/m3_brand_assignment.csv
"""

import csv
import os

import frappe

BRANDS = ["Magniflex", "Dr Back", "Cherish", "V-Rest", "B'Chhona", "MM Foam", "Reliance"]


def _detect_brand(item_code, item_name):
	u = ((item_code or "") + " " + (item_name or "")).upper()
	if "MAGNIFLEX" in u:
		return "Magniflex"
	if "DR.BACK" in u or "DR BACK" in u or "DR. BACK" in u:
		return "Dr Back"
	if "CHERISH" in u:
		return "Cherish"
	if "V-REST" in u or "VREST" in u or "V REST" in u:
		return "V-Rest"
	if "CHHONA" in u or "B'CH" in u:
		return "B'Chhona"
	if "MM FOAM" in u or "MMFOAM" in u:
		return "MM Foam"
	if "RELIANCE" in u:
		return "Reliance"
	return None


def _report_path(name):
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, name)


def _process(write):
	if write:
		for b in BRANDS:
			if not frappe.db.exists("Brand", b):
				frappe.get_doc({"doctype": "Brand", "brand": b}).insert(ignore_permissions=True)

	items = frappe.db.sql("SELECT name, item_name, brand FROM `tabItem`", as_dict=True)
	report = []
	counts = {}
	blank = 0
	for it in items:
		brand = _detect_brand(it.name, it.item_name)
		if not brand:
			blank += 1
			continue
		if it.brand == brand:
			continue  # already correct
		report.append([it.name, it.item_name, it.brand or "", brand])
		counts[brand] = counts.get(brand, 0) + 1
		if write:
			frappe.db.set_value("Item", it.name, "brand", brand, update_modified=False)

	if write:
		frappe.db.commit()

	p = _report_path("m3_brand_assignment.csv")
	with open(p, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["item_code", "item_name", "old_brand", "new_brand"])
		w.writerows(report)

	print(f"\n--- Brand assignment {'(WRITTEN)' if write else '(DRY RUN)'} ---")
	print(f"Total items         : {len(items)}")
	print(f"Will change brand   : {len(report)}")
	for b in BRANDS:
		if counts.get(b):
			print(f"    {b:<12}: {counts[b]}")
	print(f"Left blank (no rule): {blank}")
	print(f"Report              : {p}\n")
	return f"{len(report)} items branded, {blank} left blank — see m3_brand_assignment.csv"


def dry_run():
	return _process(write=False)


def run():
	return _process(write=True)
