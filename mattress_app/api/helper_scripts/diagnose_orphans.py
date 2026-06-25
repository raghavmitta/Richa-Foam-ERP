"""
Why are so many variants protected by rule 4c (replacement missing)?
Checks how many area family+thickness groups have their new standalone item.

    bench --site [site] execute mattress_app.api.diagnose_orphans.run
"""

import re

import frappe

_strip = re.compile(r"^(.*-\d+MM)-\d+-\d+$", re.IGNORECASE)


def run():
	out = []

	def line(s):
		out.append(s)
		print(s)

	all_codes = set(frappe.db.sql_list("SELECT name FROM `tabItem`"))

	variant_codes = frappe.db.sql_list(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NOT NULL AND IFNULL(custom_use_area_pricing,0)=1"""
	)
	line(f"Area variants: {len(variant_codes)}")

	# distinct replacement codes needed
	needed = {}
	unparseable = 0
	for v in variant_codes:
		m = _strip.match(v)
		if not m:
			unparseable += 1
			continue
		needed.setdefault(m.group(1), 0)
		needed[m.group(1)] += 1

	line(f"Distinct family+thickness replacements needed: {len(needed)}")
	line(f"Unparseable variant codes: {unparseable}")

	exists = [r for r in needed if r in all_codes]
	missing = [r for r in needed if r not in all_codes]
	line(f"  replacements that EXIST  : {len(exists)}")
	line(f"  replacements MISSING     : {len(missing)}")

	# how many variants are protected by the missing ones
	protected = sum(needed[r] for r in missing)
	line(f"  variants protected by missing replacements: {protected}")

	# show sample missing replacements + how many new standalone items exist total
	new_items = frappe.db.sql_list(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NULL AND IFNULL(has_variants,0)=0
		     AND IFNULL(custom_use_area_pricing,0)=1"""
	)
	line(f"\nNew standalone area items that exist: {len(new_items)}")
	line("\nSample MISSING replacements (variants kept because these don't exist):")
	for r in sorted(missing)[:25]:
		line(f"  {r}   ({needed[r]} variants)")

	# Also check: do the existing new items match the expected code format?
	line("\nSample EXISTING new standalone items:")
	for r in sorted(new_items)[:10]:
		line(f"  {r}")

	return "\n".join(out)
