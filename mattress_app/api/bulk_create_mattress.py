"""
Module 4 : Bulk-create a new mattress model's items across several thicknesses,
           with brand-first naming and area pricing.

Called by the "Create Mattress Model" dialog (client side). For each thickness
row it creates:
  - Thickness record (if missing)
  - Item  : code = "{Brand} {Model}-{thk}MM",  name = "{Brand} {Model}"
            item_group = "Products", brand = <brand>, custom_use_area_pricing = 1
  - Item Price (Standard Selling) = the 72x72 price entered for that thickness

Naming:
  family    = f"{brand} {model}"            e.g. "Dr. Back Naturalite"
  item_code = f"{family}-{thk}MM"           e.g. "Dr. Back Naturalite-250MM"
  item_name = family                        e.g. "Dr. Back Naturalite"

Server entry point (whitelisted), called from JS:
  mattress_app.api.bulk_create_mattress.create_model
"""

import json

import frappe

PRICE_LIST = "Standard Selling"
DEFAULT_GROUP = "Products"
DEFAULT_UOM = "Nos"


def _ensure_item_name(family):
	"""The custom_name dropdown on Quotation Item is a Link to 'Item Name'.
	Standalone items don't get this auto-created (the Item validate hook only
	does it for variants), so we create it explicitly."""
	if family and not frappe.db.exists("Item Name", {"item_name": family}):
		frappe.get_doc({"doctype": "Item Name", "item_name": family}).insert(ignore_permissions=True)


def _ensure_brand(brand):
	if brand and not frappe.db.exists("Brand", brand):
		frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)


def _ensure_thickness(thk_value):
	"""Create a Thickness record if missing. Returns its name."""
	# Thickness records are keyed by their own naming; match on the 'value' field.
	existing = frappe.db.get_value("Thickness", {"value": str(thk_value)}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({"doctype": "Thickness", "value": str(thk_value)})
	doc.insert(ignore_permissions=True)
	return doc.name


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


@frappe.whitelist()
def create_model(brand, model, rows, item_group=None, stock_uom=None, gst_hsn_code=None):
	"""
	brand  : brand name (also the family prefix)
	model  : model name (e.g. 'Naturalite')
	rows   : JSON list of {"thickness": 250, "price_72": 80142}
	"""
	if isinstance(rows, str):
		rows = json.loads(rows)

	brand = (brand or "").strip()
	model = (model or "").strip()
	if not brand or not model:
		frappe.throw("Brand and Model are required.")
	if not rows:
		frappe.throw("Add at least one thickness row.")

	family = f"{brand} {model}".strip()
	item_group = item_group or DEFAULT_GROUP
	stock_uom = stock_uom or DEFAULT_UOM

	_ensure_brand(brand)
	_ensure_item_name(family)

	created = []
	skipped = []
	for r in rows:
		thk = str(r.get("thickness") or "").strip()
		price = r.get("price_72")
		if not thk or not price:
			continue

		thickness_name = _ensure_thickness(thk)

		item_code = f"{family}-{thk}MM"
		if frappe.db.exists("Item", item_code):
			skipped.append(item_code)
			# backfill the thickness link + refresh price
			frappe.db.set_value(
				"Item", item_code, "custom_thickness_link", thickness_name, update_modified=False
			)
			_set_item_price(item_code, price)
			continue

		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.item_name = family  # family only (thickness lives in code)
		doc.item_group = item_group
		doc.stock_uom = stock_uom
		doc.brand = brand
		doc.custom_use_area_pricing = 1
		doc.custom_thickness_link = thickness_name
		doc.has_variants = 0
		doc.variant_of = None
		if gst_hsn_code:
			doc.gst_hsn_code = gst_hsn_code
		doc.insert(ignore_permissions=True)

		_set_item_price(item_code, price)
		created.append(item_code)

	frappe.db.commit()
	return {
		"family": family,
		"created": created,
		"skipped": skipped,
		"message": f"Created {len(created)} item(s)"
		+ (f", updated price on {len(skipped)} existing" if skipped else ""),
	}
