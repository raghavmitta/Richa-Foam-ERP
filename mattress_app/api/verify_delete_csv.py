"""
Safety check: confirm the deletion set does NOT contain any protected family
(i.e. any family+thickness whose new replacement item is missing). Run AFTER
build_keep_list and BEFORE delete_unreferenced.

    bench --site [site] execute mattress_app.api.verify_delete_csv.run
"""

import re

import frappe

_strip = re.compile(r"^(.*-\d+)[Mm][Mm]-\d+-\d+$")
KEEP_FLAG = "_mattress_keep"


def run():
	keep = set(frappe.cache().get_value(KEEP_FLAG) or [])
	if not keep:
		return "Keep list not found - run build_keep_list first."

	all_codes = set(frappe.db.sql_list("SELECT name FROM `tabItem`"))

	# the set that WOULD be deleted
	to_delete = frappe.db.sql_list(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NOT NULL
		     AND IFNULL(custom_use_area_pricing,0)=1
		     AND name NOT IN %(keep)s""",
		{"keep": tuple(keep)},
	)

	# for each, the replacement must EXIST (case-normalized) - else it's a leak
	leaks = []
	for v in to_delete:
		m = _strip.match(v)
		if not m:
			leaks.append((v, "unparseable"))
			continue
		repl = m.group(1) + "MM"
		if repl not in all_codes:
			leaks.append((v, f"replacement {repl} MISSING"))

	print(f"Items queued for deletion: {len(to_delete)}")
	if leaks:
		print(f"\n*** WARNING: {len(leaks)} items would be deleted WITHOUT a replacement! ***")
		for v, why in leaks[:30]:
			print(f"   {v}  ({why})")
		return f"UNSAFE: {len(leaks)} leaks - do NOT delete."
	print("\nAll queued items have a valid replacement. Safe to delete.")
	return f"SAFE: {len(to_delete)} items, all with replacements."
