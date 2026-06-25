"""
For each family+thickness whose NEW standalone item is missing, explain WHY
create_family_thickness_items didn't create it.

The creation script collects groups from Item Price rows where:
  price_list = 'Standard Selling', price_list_rate > 0,
  variant_of IS NOT NULL, custom_use_area_pricing = 1
Then for each (family, thickness) it creates "{family}-{thk}MM".

So a missing one means: that family+thickness had NO qualifying Item Price row.

    bench --site [site] execute mattress_app.api.diagnose_missing_items.run
"""

import re

import frappe

_strip = re.compile(r"^(.*-\d+)[Mm][Mm]-\d+-\d+$")
_fam_thk = re.compile(r"^(.*)-(\d+)MM$", re.IGNORECASE)


def run():
	out = []

	def line(s):
		out.append(s)
		print(s)

	all_codes = set(frappe.db.sql_list("SELECT name FROM `tabItem`"))

	# find the missing replacements (same logic as cleanup)
	variant_codes = frappe.db.sql_list(
		"""SELECT name FROM `tabItem`
		   WHERE variant_of IS NOT NULL AND IFNULL(custom_use_area_pricing,0)=1"""
	)
	missing = {}
	for v in variant_codes:
		m = _strip.match(v)
		if not m:
			continue
		repl = m.group(1) + "MM"
		if repl not in all_codes:
			missing.setdefault(repl, []).append(v)

	line(f"Missing replacements: {len(missing)}\n")

	for repl in sorted(missing):
		fm = _fam_thk.match(repl)
		if not fm:
			line(f"{repl}: cannot parse family/thickness")
			continue
		family, thk = fm.group(1), fm.group(2)

		# how many variants of this family+thickness exist?
		n_variants = len(missing[repl])

		# do ANY of those variants have a Standard Selling price > 0?
		priced = frappe.db.sql(
			"""SELECT COUNT(*) FROM `tabItem Price` ip
			   INNER JOIN `tabItem` i ON i.name = ip.item_code
			   WHERE ip.price_list='Standard Selling' AND ip.price_list_rate>0
			     AND i.item_name=%s
			     AND i.name LIKE %s""",
			(family, f"%-{thk}MM-%"),
		)[0][0]

		# does a 72x72 variant exist for it, and is it priced?
		base72 = frappe.db.sql(
			"""SELECT i.name, IFNULL(ip.price_list_rate,0) AS rate
			   FROM `tabItem` i
			   LEFT JOIN `tabItem Price` ip
			     ON ip.item_code=i.name AND ip.price_list='Standard Selling'
			   WHERE i.item_name=%s AND i.name LIKE %s""",
			(family, f"%-{thk}MM-72-72"),
			as_dict=True,
		)
		base_info = "none"
		if base72:
			base_info = f"{base72[0].name} rate={base72[0].rate}"

		# is the family+thickness flagged area-priced?
		area_flag = frappe.db.sql(
			"""SELECT COUNT(*) FROM `tabItem`
			   WHERE item_name=%s AND name LIKE %s AND IFNULL(custom_use_area_pricing,0)=1""",
			(family, f"%-{thk}MM-%"),
		)[0][0]

		reason = (
			"NO priced variant (Standard Selling rate>0)"
			if priced == 0
			else f"{priced} priced variants exist - SHOULD have been created?"
		)
		line(f"{repl}")
		line(f"   variants={n_variants}  priced_variants={priced}  area_flagged={area_flag}")
		line(f"   72x72 base: {base_info}")
		line(f"   -> {reason}\n")

	return "\n".join(out)
