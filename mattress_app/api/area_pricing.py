"""
get_item_details OVERRIDE for area-priced mattresses.

WHY
  ERPNext's get_item_details / apply_price_list returns the item's raw Item
  Price (the 72x72 base price) for area-priced items. That causes:
    - a live flicker to the base price on customer / price-list change
    - the base price (not the size price) feeding discounts on save
  Patching after the fact (a before_validate hook) double-applies discounts.

FIX
  Override get_item_details with a THIN wrapper:
    - For NON area-priced items  -> return core result UNCHANGED.
    - For area-priced items      -> replace price_list_rate & rate with the
      size-calculated area price (72x72 price / 5184 * roundedL * roundedW),
      and let ERPNext's normal discount flow run on top.

WIRE IN hooks.py:
    override_whitelisted_methods = {
        "erpnext.stock.get_item_details.get_item_details":
            "mattress_app.api.area_pricing.get_item_details",
        "erpnext.stock.get_item_details.apply_price_list":
            "mattress_app.api.area_pricing.apply_price_list",
    }

(If you already override other whitelisted methods, add this key alongside.)
Place this file as mattress_app/api/area_pricing.py (or merge into quotation.py
and point the hook there).
"""

import json
import math

import frappe
from erpnext.stock.get_item_details import (
	apply_price_list as _core_apply_price_list,
)
from erpnext.stock.get_item_details import (
	get_item_details as _core_get_item_details,
)

LEN_STEP = 3
WID_STEP = 6
BASE_AREA = 72 * 72  # 5184


def _round_to_grid(value, step):
	value = float(value or 0)
	if value <= 0:
		return 0
	frac = value - math.floor(value)
	whole = math.floor(value) if frac <= 0.5 else math.ceil(value)
	if whole % step == 0:
		return whole
	return whole + (step - (whole % step))


def _as_dict(args):
	if isinstance(args, str):
		try:
			return json.loads(args)
		except Exception:
			return frappe._dict()
	return args or frappe._dict()


def _base_72_price(item_code, price_list):
	"""Always read the 72x72 base price from the Item Price master, so the
	calculation is deterministic regardless of what core returned."""
	return frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list or "Standard Selling", "selling": 1},
		"price_list_rate",
	)


def _area_price_from(base_price, length, width):
	"""Return the size-calculated area price, or None if not computable."""
	if not base_price or not length or not width:
		return None
	rate_per_sqin = float(base_price) / BASE_AREA
	rounded_l = _round_to_grid(length, LEN_STEP)
	rounded_w = _round_to_grid(width, WID_STEP)
	return round(rate_per_sqin * rounded_l * rounded_w), rounded_l, rounded_w


def _dims_from_doc(doc, child_docname):
	"""Pull custom_length/custom_width for a given child row out of the doc
	payload passed to get_item_details. Handles doc as JSON string, dict, or
	Document. Returns (length, width) or (None, None)."""
	if not doc:
		return None, None
	d = doc
	if isinstance(d, str):
		try:
			d = json.loads(d)
		except Exception:
			return None, None
	# dict-like
	items = None
	if isinstance(d, dict):
		items = d.get("items")
	else:
		items = getattr(d, "items", None)
		# a Document.items is a method? no - it's the child table list
	if not items:
		return None, None
	for it in items:
		row = it if isinstance(it, dict) else it.__dict__
		nm = row.get("name")
		if child_docname and nm == child_docname:
			return row.get("custom_length"), row.get("custom_width")
	# fallback: if only one row, use it
	if len(items) == 1:
		row = items[0] if isinstance(items[0], dict) else items[0].__dict__
		return row.get("custom_length"), row.get("custom_width")
	return None, None


@frappe.whitelist()
def get_item_details(args, doc=None, for_validate=False, overwrite_warehouse=True):
	# 1) always run the core method first - everything behaves as standard
	out = _core_get_item_details(
		args, doc=doc, for_validate=for_validate, overwrite_warehouse=overwrite_warehouse
	)

	a = _as_dict(args)
	item_code = a.get("item_code") or out.get("item_code")
	if not item_code:
		return out

	# 2) only act on area-priced items; everything else passes through
	if not frappe.db.get_value("Item", item_code, "custom_use_area_pricing"):
		return out

	# 3) get the line dimensions. ERPNext does NOT put custom_length/width in
	#    args, and the child row may be unsaved (__islocal), so we read them
	#    from the `doc` payload (the whole document is passed to this method),
	#    matching the child row by child_docname.
	length = a.get("custom_length")
	width = a.get("custom_width")
	if not length or not width:
		l, w = _dims_from_doc(doc, a.get("child_docname"))
		length = length or l
		width = width or w

	if not length or not width:
		# no dimensions yet -> leave core result (base 72x72 price) as-is
		return out

	# 4) ALWAYS read the 72x72 base from the Item Price master (deterministic)
	base_price = _base_72_price(item_code, a.get("price_list"))
	if not base_price:
		return out

	rate_per_sqin = float(base_price) / BASE_AREA
	rounded_l = _round_to_grid(length, LEN_STEP)
	rounded_w = _round_to_grid(width, WID_STEP)
	area_price = round(rate_per_sqin * rounded_l * rounded_w)

	# 5) substitute the size price as the list price (MRP). Leave discount
	#    fields untouched so ERPNext applies the line discount on top once.
	out["price_list_rate"] = area_price
	out["base_price_list_rate"] = area_price
	out["rate"] = area_price
	out["base_rate"] = area_price
	# keep MRP reference field if present
	out["custom_item_price_rate"] = area_price

	return out


@frappe.whitelist()
def apply_price_list(args, as_doc=False, doc=None):
	# 1) run core - everything behaves as standard
	result = _core_apply_price_list(args, as_doc=as_doc, doc=doc)

	a = _as_dict(args)
	in_rows = a.get("items") or []
	# also pull rows from doc payload as a fallback dim source
	doc_d = doc
	if isinstance(doc_d, str):
		try:
			doc_d = json.loads(doc_d)
		except Exception:
			doc_d = None
	doc_rows = (doc_d.get("items") if isinstance(doc_d, dict) else None) or []

	# map child_docname -> row (prefer args row, fall back to doc row) for dims
	by_name = {}
	for r in list(in_rows) + list(doc_rows):
		rr = _as_dict(r)
		key = rr.get("name") or rr.get("child_docname")
		if not key:
			continue
		if key not in by_name:
			by_name[key] = rr
		else:
			# merge dims if missing
			if not by_name[key].get("custom_length") and rr.get("custom_length"):
				by_name[key]["custom_length"] = rr.get("custom_length")
			if not by_name[key].get("custom_width") and rr.get("custom_width"):
				by_name[key]["custom_width"] = rr.get("custom_width")

	# result may be a dict with 'children', or (as_doc) a doc-like structure
	children = None
	if isinstance(result, dict):
		children = result.get("children")
	if children is None:
		return result

	for child in children:
		c = _as_dict(child)
		# core's children often omit item_code - get it from the matching
		# input/doc row instead.
		src = by_name.get(c.get("name")) or by_name.get(c.get("child_docname")) or {}
		item_code = c.get("item_code") or src.get("item_code")
		if not item_code:
			continue
		if not frappe.db.get_value("Item", item_code, "custom_use_area_pricing"):
			continue  # non-area: leave core result untouched

		length = src.get("custom_length")
		width = src.get("custom_width")
		base_price = _base_72_price(item_code, a.get("price_list"))
		computed = _area_price_from(base_price, length, width)
		if not computed:
			continue
		area_price, rl, rw = computed

		child["price_list_rate"] = area_price
		child["base_price_list_rate"] = area_price
		child["rate"] = area_price
		child["base_rate"] = area_price
		child["custom_item_price_rate"] = area_price

	return result
