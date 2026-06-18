"""
Phase B-NEW (Module 2) : Create one item per area-priced family+thickness, and
                         store its 72x72 PRICE as an Item Price (Standard Selling).

For each area-priced (family, thickness) group:
  - new item        = "Family-ThicknessMM"  (e.g. "Dr Back Naturalite-250MM")
  - settings copied from the 72x72 base variant (UOM, item_group, tax, HSN, brand)
  - custom_use_area_pricing = 1   (flag only; NO rate stored on the item)
  - Item Price (Standard Selling).price_list_rate = the 72x72 price
       (taken from the 72x72 base variant's own Item Price; fallback = closest size
        scaled to 72x72 area so the derived rate is preserved)

The resolver derives rate = price_list_rate / 5184 and prices any size from it.
Discounts / offers / % increases are then native ERPNext (Pricing Rule / Price List).

    bench --site [site] execute mattress_app.api.create_family_thickness_items.dry_run
    bench --site [site] execute mattress_app.api.create_family_thickness_items.run

Report: sites/[site]/private/files/bnew_created_items.csv
"""

import csv
import os
import re

import frappe

CODE_RE = re.compile(r"^(.+?)-(\d+)[Mm][Mm]-(\d+)-(\d+)$")
BASE_L, BASE_W = 72, 72
BASE_AREA = BASE_L * BASE_W
PRICE_LIST = "Standard Selling"

COPY_FIELDS = [
	"item_group",
	"stock_uom",
	"is_stock_item",
	"include_item_in_manufacturing",
	"is_sales_item",
	"is_purchase_item",
	"gst_hsn_code",
	"country_of_origin",
	"brand",
	"description",
	"is_fixed_asset",
]


def _report_path(name):
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, name)


def _collect_groups():
	"""(family, thickness) -> {(l,w): (item_code, price_72_or_scaled)}"""
	rows = frappe.db.sql(
		"""
		SELECT ip.item_code, ip.price_list_rate, i.variant_of
		FROM `tabItem Price` ip
		INNER JOIN `tabItem` i ON i.name = ip.item_code
		WHERE ip.price_list = %s
		  AND ip.price_list_rate > 0
		  AND i.variant_of IS NOT NULL
		  AND IFNULL(i.custom_use_area_pricing,0) = 1
		""",
		(PRICE_LIST,),
		as_dict=True,
	)
	groups = {}
	for r in rows:
		m = CODE_RE.match(r.item_code)
		if not m:
			continue
		fam, thk = m.group(1), m.group(2)
		l, w = int(m.group(3)), int(m.group(4))
		groups.setdefault((fam, thk), {})[(l, w)] = (r.item_code, r.price_list_rate)
	return groups


def _plan():
	groups = _collect_groups()
	plan = []
	for (fam, thk), sizes in sorted(groups.items()):
		new_code = f"{fam}-{thk}MM"
		if (BASE_L, BASE_W) in sizes:
			base_ic, base_price = sizes[(BASE_L, BASE_W)]
			price_72 = base_price
			base_type = "72x72"
		else:
			# no 72x72 -> scale closest size's price to the 72x72 area so the
			# derived rate (price_72/5184) equals that size's rate.
			closest = min(sizes.keys(), key=lambda k: abs(k[0] - BASE_L) + abs(k[1] - BASE_W))
			base_ic, base_price = sizes[closest]
			rate = base_price / (closest[0] * closest[1])
			price_72 = round(rate * BASE_AREA, 2)
			base_type = f"fallback {closest[0]}x{closest[1]} scaled"
		plan.append(
			{
				"new_code": new_code,
				"base_ic": base_ic,
				"family": fam,
				"price_72": price_72,
				"base_type": base_type,
			}
		)
	return plan


def dry_run():
	plan = _plan()
	rows = [
		[
			p["new_code"],
			p["base_ic"],
			p["price_72"],
			round(p["price_72"] / BASE_AREA, 6),
			p["base_type"],
			"EXISTS" if frappe.db.exists("Item", p["new_code"]) else "will create",
		]
		for p in plan
	]
	pth = _report_path("bnew_created_items.csv")
	with open(pth, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(
			["new_item_code", "settings_from", "price_72x72", "derived_rate_per_sqin", "base_type", "status"]
		)
		w.writerows(rows)
	exists = sum(1 for p in plan if frappe.db.exists("Item", p["new_code"]))
	print("\n--- Create Family+Thickness items DRY RUN ---")
	print(f"Groups        : {len(plan)}")
	print(f"Already exist : {exists}")
	print(f"Will create   : {len(plan) - exists}")
	print(f"Report        : {pth}\n")
	return f"{len(plan)} groups, {len(plan)-exists} to create — see bnew_created_items.csv"


import re as _re

_THK_CODE_RE = _re.compile(r"-(\d+)MM$", _re.IGNORECASE)


def _parse_thk(code):
	m = _THK_CODE_RE.search(code or "")
	return m.group(1) if m else None


def _thickness_name(thk_val):
	"""Find the Thickness record whose value matches thk_val. Returns name or None."""
	return frappe.db.get_value("Thickness", {"value": str(thk_val)}, "name")


def _ensure_item_name(family):
	"""custom_name dropdown is a Link to 'Item Name'. Ensure the family exists
	there (old variants usually created it, but be safe for new families)."""
	if family and not frappe.db.exists("Item Name", {"item_name": family}):
		frappe.get_doc({"doctype": "Item Name", "item_name": family}).insert(ignore_permissions=True)


def _set_item_price(item_code, price):
	existing = frappe.get_all(
		"Item Price",
		filters={"item_code": item_code, "price_list": PRICE_LIST, "selling": 1},
		fields=["name"],
	)
	if existing:
		frappe.db.set_value("Item Price", existing[0].name, "price_list_rate", price)
	else:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": PRICE_LIST,
				"selling": 1,
				"price_list_rate": price,
			}
		).insert(ignore_permissions=True)


def run():
	plan = _plan()
	created = 0
	priced = 0
	skipped = 0
	log = []
	for p in plan:
		new_code = p["new_code"]
		_ensure_item_name(p["family"])
		if frappe.db.exists("Item", new_code):
			skipped += 1
			# Fix item_name to family-only on already-created items (idempotent).
			current_name = frappe.db.get_value("Item", new_code, "item_name")
			if current_name != p["family"]:
				frappe.db.set_value("Item", new_code, "item_name", p["family"], update_modified=False)
			# backfill the thickness link
			_thk = _parse_thk(new_code)
			if _thk:
				_tn = _thickness_name(_thk)
				if _tn:
					frappe.db.set_value("Item", new_code, "custom_thickness_link", _tn, update_modified=False)
		else:
			base = frappe.get_doc("Item", p["base_ic"])
			doc = frappe.new_doc("Item")
			doc.item_code = new_code
			doc.item_name = p[
				"family"
			]  # family only (e.g. "Dr Back Naturalite"); thickness lives in code/column
			for f in COPY_FIELDS:
				if base.get(f) is not None:
					doc.set(f, base.get(f))
			doc.has_variants = 0
			doc.variant_of = None
			doc.custom_use_area_pricing = 1
			_thk = _parse_thk(new_code)
			if _thk:
				doc.custom_thickness_link = _thickness_name(_thk)
			doc.insert(ignore_permissions=True)
			created += 1
		# always (re)set the 72x72 price as the Item Price
		_set_item_price(new_code, p["price_72"])
		priced += 1
		log.append(
			[new_code, p["base_ic"], p["price_72"], round(p["price_72"] / BASE_AREA, 6), p["base_type"]]
		)
	frappe.db.commit()

	pth = _report_path("bnew_created_items.csv")
	with open(pth, "w", newline="", encoding="utf-8") as f:
		w = csv.writer(f)
		w.writerow(["new_item_code", "settings_from", "price_72x72", "derived_rate_per_sqin", "base_type"])
		w.writerows(log)
	msg = (
		f"Created {created} items, priced {priced} (72x72 Item Price set), "
		f"updated {skipped} existing (item_name set to family). Report: {pth}"
	)
	print(msg)
	return msg
