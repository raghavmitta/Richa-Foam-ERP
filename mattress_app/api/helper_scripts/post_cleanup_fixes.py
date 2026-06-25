"""
Post-cleanup fixes:

FIX 1 — Protected old variants must NOT be area-priced.
  Variants kept by rule 4c (no new replacement item) still have
  custom_use_area_pricing = 1, so the override computes a wrong area price.
  They should use their OWN stored Item Price (old behaviour), so we turn the
  flag OFF for every surviving VARIANT (variant_of NOT NULL). New standalone
  items (variant_of NULL) keep the flag ON.

FIX 2 — Refresh stale item_name on Item Price.
  Item Price caches item_name from the Item at creation time. Items created
  before the family-only rename still show "Family-ThicknessMM" on their Item
  Price rows. Re-sync Item Price.item_name from the current Item.item_name.

    bench --site [site] execute mattress_app.api.post_cleanup_fixes.preview
    bench --site [site] execute mattress_app.api.post_cleanup_fixes.run
"""

import frappe


def preview():
	out = []

	def line(s):
		out.append(s)
		print(s)

	# FIX 1 scope: surviving variants still flagged area-priced
	bad_flag = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabItem`
		   WHERE variant_of IS NOT NULL AND IFNULL(custom_use_area_pricing,0)=1"""
	)[0][0]
	line(f"FIX 1 - variants still area-flagged (will turn OFF): {bad_flag}")

	# FIX 2 scope: Item Price rows whose item_name != the Item's current name
	stale = frappe.db.sql(
		"""SELECT COUNT(*) FROM `tabItem Price` ip
		   INNER JOIN `tabItem` i ON i.name = ip.item_code
		   WHERE IFNULL(ip.item_name,'') != IFNULL(i.item_name,'')"""
	)[0][0]
	line(f"FIX 2 - Item Price rows with stale item_name (will refresh): {stale}")

	return "\n".join(out)


def run():
	# FIX 1: turn off area pricing on surviving old variants
	frappe.db.sql(
		"""UPDATE `tabItem`
		   SET custom_use_area_pricing = 0
		   WHERE variant_of IS NOT NULL AND IFNULL(custom_use_area_pricing,0)=1"""
	)
	fixed_flags = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

	# FIX 2: refresh Item Price.item_name from the current Item.item_name
	frappe.db.sql(
		"""UPDATE `tabItem Price` ip
		   INNER JOIN `tabItem` i ON i.name = ip.item_code
		   SET ip.item_name = i.item_name
		   WHERE IFNULL(ip.item_name,'') != IFNULL(i.item_name,'')"""
	)
	fixed_names = frappe.db.sql("SELECT ROW_COUNT()")[0][0]

	frappe.db.commit()
	msg = (
		f"Done. Turned OFF area flag on {fixed_flags} surviving variants; "
		f"refreshed item_name on {fixed_names} Item Price rows."
	)
	print(msg)
	return msg
