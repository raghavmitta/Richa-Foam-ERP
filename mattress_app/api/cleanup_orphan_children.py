"""
Clean up ORPHANED child-table rows: rows in item child tables whose parent
Item no longer exists. This happens if items were deleted without cascading
their children (e.g. an earlier delete run without the cascade).
SAFE: only deletes child rows where the parent item_code/parent is NOT in
tabItem. Never touches rows belonging to surviving items.
    bench --site [site] execute mattress_app.api.cleanup_orphan_children.preview
    bench --site [site] execute mattress_app.api.cleanup_orphan_children.run
"""

import frappe

# (DocType Name, column that references Item.name)
_CHILD_DOCTYPES = [
	("Item Variant Attribute", "parent"),
	("Item Default", "parent"),
	("UOM Conversion Detail", "parent"),
	("Item Price", "item_code"),
	("Item Barcode", "parent"),
	("Item Reorder", "parent"),
	("Item Tax", "parent"),
	("Item Manufacturer", "item_code"),
]


def _counts():
	rows = []
	for dt, col in _CHILD_DOCTYPES:
		# frappe.db.table_exists expects the DocType name, not the 'tab...' name
		if not frappe.db.table_exists(dt):
			continue

		tbl = f"tab{dt}"
		total = frappe.db.sql(f"SELECT COUNT(*) FROM `{tbl}`")[0][0]
		orphans = frappe.db.sql(
			f"""SELECT COUNT(*) FROM `{tbl}` c
               LEFT JOIN `tabItem` i ON i.name = c.`{col}`
               WHERE i.name IS NULL"""
		)[0][0]
		rows.append((tbl, col, total, orphans))
	return rows


def preview():
	out = ["ORPHAN CHILD-ROW PREVIEW (nothing deleted):"]
	for tbl, _col, total, orphans in _counts():
		out.append(f"  {tbl:32} total={total:>8}  orphans={orphans:>8}")
	msg = "\n".join(out)
	print(msg)
	return msg


def run(batch_size=5000):
	total_deleted = 0
	for dt, col in _CHILD_DOCTYPES:
		if not frappe.db.table_exists(dt):
			continue

		tbl = f"tab{dt}"
		tbl_deleted = 0

		while True:
			# Collect a batch of orphan PRIMARY KEYS (name), then delete by name.
			# (Multi-table DELETE ... LIMIT is NOT valid in MariaDB, so we do a
			# single-table delete keyed on the orphan row names.)
			orphan_names = frappe.db.sql(
				f"""SELECT c.name FROM `{tbl}` c
                   LEFT JOIN `tabItem` i ON i.name = c.`{col}`
                   WHERE i.name IS NULL
                   LIMIT {int(batch_size)}"""
			)
			if not orphan_names:
				break

			names = [r[0] for r in orphan_names]
			ph = ", ".join(["%s"] * len(names))

			frappe.db.sql(f"DELETE FROM `{tbl}` WHERE name IN ({ph})", names)
			frappe.db.commit()

			tbl_deleted += len(names)
			total_deleted += len(names)
			print(f"  {tbl}: deleted {tbl_deleted} orphan rows so far...")

	msg = f"Orphan cleanup complete. Deleted {total_deleted} orphaned child rows."
	print(msg)
	return msg


def optimize():
	for dt, _ in _CHILD_DOCTYPES:
		if frappe.db.table_exists(dt):
			tbl = f"tab{dt}"
			frappe.db.sql(f"OPTIMIZE TABLE `{tbl}`")
			print(f"  optimized {tbl}")
	return "Optimize complete."
