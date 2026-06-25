"""
Quotation status logic - writes the FULL stage into custom_status, including
native lifecycle states (Ordered, Cancelled, Lost, Expired) read from the
native status field. The JS just reads custom_status and displays it.

Wire in hooks.py under Quotation:
    "validate":    "...quotation.derive_quotation_status"
    "on_update":   "...quotation.apply_quotation_status"   (catches native status changes)
And call apply_status_for(doctype, name) from advance_linker.updateAdvancePaidSilently.
"""

import hashlib
import math
import os

import frappe
from frappe import _, _dict
from frappe.utils import flt
from frappe.utils.pdf import get_pdf

LEN_STEP = 3
WID_STEP = 6
# Field holding the advance amount (label "Advance Paid")
ADVANCE_FIELD = "advance_paid"
# Option A: write to the native status field


def _compute_status(adv, size, revisit, docstatus, native_status):
	# Priority: native lifecycle facts ALWAYS win over the draft journey.
	# 1) Cancelled (doc cancelled or marked Cancelled).
	if docstatus == 2 or native_status == "Cancelled":
		return "Cancelled"
	# 2) Ordered / Partially Ordered (a Sales Order exists - real fact).
	if native_status in ("Ordered", "Partially Ordered"):
		return native_status
	# 3) Lost / Expired (explicitly marked - win even in draft).
	if native_status in ("Lost", "Expired"):
		return native_status
	# 4) Submitted (none of the above) -> Confirmed.
	if docstatus == 1:
		return "Confirmed"
	# 5) DRAFT journey (from checkboxes + revisit date).
	if adv and size:
		return "Confirmation Pending"
	if adv and not size:
		return "Size Pending"
	if size and not adv:
		return "Advance Pending"
	if revisit:
		return "Revisit Pending"
	return "Draft"


def _derive(doc):
	if flt(doc.get(ADVANCE_FIELD)) > 0 and not doc.get("custom_advance_received"):
		doc.custom_advance_received = 1
	return _compute_status(
		bool(doc.get("custom_advance_received")),
		bool(doc.get("custom_size_confirmed")),
		bool(doc.get("custom_revisit_date")),
		doc.docstatus,
		doc.get("status"),
	)


def derive_quotation_status(doc, method=None):
	"""validate hook: set custom_status from fields + native status."""
	new_status = _derive(doc)
	if new_status:
		doc.custom_status = new_status


def apply_quotation_status(doc, method=None):
	"""on_update hook: re-sync custom_status after ERPNext changes native status
	(e.g. when a Sales Order is created -> Ordered, or on cancel). db_set so it
	persists without another validate cycle."""
	new_status = _compute_status(
		bool(doc.get("custom_advance_received")),
		bool(doc.get("custom_size_confirmed")),
		bool(doc.get("custom_revisit_date")),
		doc.docstatus,
		doc.get("status"),
	)
	if new_status and new_status != doc.get("custom_status"):
		doc.db_set("custom_status", new_status, update_modified=False)


def apply_status_for(doctype, name):
	"""Called from the advance tracker (db.set_value bypasses validate)."""
	if doctype != "Quotation":
		return
	v = frappe.db.get_value(
		"Quotation",
		name,
		[
			"advance_paid",
			"custom_advance_received",
			"custom_size_confirmed",
			"custom_revisit_date",
			"docstatus",
			"status",
		],
		as_dict=True,
	)
	if not v:
		return
	adv = bool(v.custom_advance_received)
	if flt(v.advance_paid) > 0 and not adv:
		adv = True
		frappe.db.set_value("Quotation", name, "custom_advance_received", 1, update_modified=False)
	new_status = _compute_status(
		adv,
		bool(v.custom_size_confirmed),
		bool(v.custom_revisit_date),
		v.docstatus,
		v.status,
	)
	if new_status:
		frappe.db.set_value("Quotation", name, "custom_status", new_status, update_modified=False)


def set_cancelled_status(doc, method=None):
	"""Quotation on_cancel hook: cancellation bypasses validate/on_update, so
	set custom_status to Cancelled here directly."""
	doc.db_set("custom_status", "Cancelled", update_modified=False)


def sync_quotation_from_sales_order(doc, method=None):
	"""Sales Order on_submit / on_cancel hook.

	When an SO is submitted, ERPNext sets the source quotation(s) status to
	'Ordered' via a direct db write (bypassing the quotation's own hooks). On
	cancel, it reverts them. Either way, re-sync each source quotation's
	custom_status so our stored stage reflects the new native status.
	"""
	# Collect the source quotation names from the SO items.
	qtns = set()
	for it in doc.get("items") or []:
		q = it.get("prevdoc_docname") or it.get("against_quotation")
		if q:
			qtns.add(q)
	for q in qtns:
		apply_status_for("Quotation", q)


def require_confirmations_before_submit(doc, method=None):
	"""before_submit hook: block submission unless BOTH advance received and
	size confirmed are ticked."""
	import frappe

	missing = []
	if not doc.get("custom_advance_received"):
		missing.append("Advance Received")
	if not doc.get("custom_size_confirmed"):
		missing.append("Size Confirmed")
	if missing:
		frappe.throw(
			"Cannot submit: please tick " + " and ".join(missing) + " before confirming this quotation."
		)


def get_attribute_values(attribute_name):
	"""Return sorted numeric values for the given attribute (Length/Width)."""
	rows = frappe.db.sql(
		"""
        SELECT CAST(attribute_value AS DECIMAL(10,2)) AS val
        FROM `tabItem Attribute Value`
        WHERE parent = %s
        ORDER BY val
    """,
		attribute_name,
		as_dict=True,
	)

	return [float(r.val) for r in rows]


def pick_standard_value(custom, standards):
	"""
	Mattress rule:
	- If custom between two standard values:
	    diff = custom - lower
	    diff <= 0.5 -> lower
	    diff > 0.5  -> higher
	"""
	standards = sorted(standards)

	if custom <= standards[0]:
		return standards[0]
	if custom >= standards[-1]:
		return standards[-1]

	for i in range(len(standards) - 1):
		low = standards[i]
		high = standards[i + 1]
		if low <= custom <= high:
			diff = custom - low
			return low if diff <= 0.5 else high

	return standards[-1]


def _round_to_grid(value, step):
	"""decimal <=.5 down / >.5 up to whole, then UP to next multiple of step. Unbounded."""
	value = float(value)
	frac = value - math.floor(value)
	whole = math.floor(value) if frac <= 0.5 else math.ceil(value)
	if whole % step == 0:
		return whole
	return whole + (step - (whole % step))


def _area_item_code(custom_name, thk_val):
	code = f"{custom_name}-{thk_val}MM"
	if frappe.db.exists("Item", code):
		return code
	return None


@frappe.whitelist()
def get_mattress_variant(custom_length, custom_width, custom_thickness, custom_name, price_list=None):
	"""Resolve the order line's item_code from family + thickness and round the
	dimensions to grid. Pricing is handled entirely by the get_item_details /
	apply_price_list override once item_code is set, so NO price is computed
	here. This function only:
	  1) resolves the item_code (area item, or snapped fixed-price variant)
	  2) returns the rounded "standard" dimensions
	  3) shows the Custom vs Standard dimension popup
	"""
	custom_length = float(custom_length)
	custom_width = float(custom_width)
	thickness_value = frappe.db.get_value("Thickness", custom_thickness, "value")
	thk_val = (
		str(int(float(thickness_value)))
		if thickness_value and float(thickness_value).is_integer()
		else str(thickness_value)
	)

	area_code = _area_item_code(custom_name, thk_val)

	if area_code:
		# ---- AREA ITEM: resolve code + round dims + show popup (no pricing) ----
		rounded_l = _round_to_grid(custom_length, LEN_STEP)
		rounded_w = _round_to_grid(custom_width, WID_STEP)

		if custom_length < custom_width:
			frappe.msgprint("<span style='color:red;'>Dimensions: Length is less than Width</span>")
		frappe.msgprint(f"""
		<table class="table table-bordered">
			<tr><th>Type</th><th>Thickness (mm)</th><th>Length (inch)</th><th>Width (inch)</th></tr>
			<tr><td><b>Custom</b></td><td>{thk_val}</td><td>{custom_length}</td><td>{custom_width}</td></tr>
			<tr><td><b>Standard</b></td><td>{thk_val}</td><td>{rounded_l}</td><td>{rounded_w}</td></tr>
		</table>
		""")

		return {
			"selected_length": rounded_l,
			"selected_width": rounded_w,
			"selected_thickness": thk_val,
			"variant_item": area_code,
			"is_area": True,
		}

	# ---- FIXED-PRICE PATH (Magniflex, pillows): snap to standard variant ----
	standard_lengths = get_attribute_values("Length")
	standard_widths = get_attribute_values("Width")
	selected_length = pick_standard_value(custom_length, standard_lengths)
	selected_width = pick_standard_value(custom_width, standard_widths)
	len_val = str(int(selected_length)) if float(selected_length).is_integer() else str(selected_length)
	wid_val = str(int(selected_width)) if float(selected_width).is_integer() else str(selected_width)

	variant_item = frappe.db.sql(
		"""
		SELECT item.name
		FROM `tabItem` item
		INNER JOIN `tabItem Variant Attribute` len_attr
			ON len_attr.parent = item.name AND len_attr.attribute = 'Length'
			AND len_attr.attribute_value = %s
		INNER JOIN `tabItem Variant Attribute` wid_attr
			ON wid_attr.parent = item.name AND wid_attr.attribute = 'Width'
			AND wid_attr.attribute_value = %s
		INNER JOIN `tabItem Variant Attribute` thk_attr
			ON thk_attr.parent = item.name AND thk_attr.attribute = 'Thickness mm'
			AND thk_attr.attribute_value = %s
		WHERE item.item_name = %s
		LIMIT 1
		""",
		(len_val, wid_val, thk_val, custom_name),
		as_dict=True,
	)
	item_code = variant_item[0].name if variant_item else None

	if item_code:
		frappe.msgprint(f"""
		<table class="table table-bordered">
			<tr><th>Type</th><th>Thickness (mm)</th><th>Length (inch)</th><th>Width (inch)</th></tr>
			<tr><td><b>Custom</b></td><td>{thk_val}</td><td>{custom_length}</td><td>{custom_width}</td></tr>
			<tr><td><b>Standard</b></td><td>{thk_val}</td><td>{selected_length}</td><td>{selected_width}</td></tr>
		</table>
		""")

	return {
		"selected_length": selected_length,
		"selected_width": selected_width,
		"selected_thickness": thk_val,
		"variant_item": item_code,
		"is_area": False,
	}


#################RATE LOWER THAN ITEM PRICE WARNING MESSAGE#####################
def rate_lower_warning(doc, method):
	for item in doc.items:
		if item.custom_item_price_rate > 0 and item.price_list_rate < item.custom_item_price_rate:
			mrp = frappe.format_value(
				item.custom_item_price_rate, {"fieldtype": "Currency", "options": doc.currency}
			)
			frappe.msgprint(
				f"""
                <span>
                    ⚠️ <b>{item.item_code}</b>: The rate is lower than MRP ({mrp}).
                </span>
                """
			)


################ITEM PRICE DISCOUNT LOGIC##########################
def additional_discount(doc, method=None):
	discountable_items = []
	discountable_total = 0

	for item in doc.items:
		discount_flag = frappe.db.get_value("Item", item.item_code, "custom_discount_applicable") or 0

		if discount_flag == 0:
			base_amount = item.amount or 0
			discountable_items.append(item)
			discountable_total += base_amount
		else:
			item.distributed_discount_amount = 0
			item.discount_percentage = 0
			item.net_amount = item.amount
			item.net_rate = item.rate
			item.base_net_amount = item.base_amount
			item.base_net_rate = item.base_rate
			item.taxable_value = item.net_amount
			item.base_taxable_value = item.base_net_amount

	if not discountable_items:
		doc.discount_amount = 0
		doc.additional_discount_percentage = 0
		return

	if doc.additional_discount_percentage:
		total_discount = (discountable_total * doc.additional_discount_percentage) / 100
	else:
		total_discount = doc.discount_amount or 0

	if total_discount <= 0:
		return

	if total_discount > discountable_total:
		frappe.throw("Additional discount cannot exceed total of discountable items.")

	remaining = total_discount

	for idx, item in enumerate(discountable_items):
		if idx == len(discountable_items) - 1:
			distributed = remaining
		else:
			distributed = frappe.utils.flt(
				(item.amount / discountable_total) * total_discount, doc.precision("discount_amount")
			)

		item.distributed_discount_amount = distributed
		item.net_amount = item.amount - distributed
		item.net_rate = item.net_amount / item.qty if item.qty else 0
		item.base_net_amount = item.base_amount - distributed
		item.base_net_rate = item.base_net_amount / item.qty if item.qty else 0
		item.taxable_value = item.net_amount
		item.base_taxable_value = item.base_net_amount
		remaining -= distributed


@frappe.whitelist()
def is_non_discount_item(item_code):
	return frappe.db.get_value("Item", item_code, "custom_discount_applicable") or 0


##################ADDRESS MANDATORY###############
def address_mandatory_check(doc, method):
	if not doc.address_display:
		frappe.throw(_("Please select Address before submitting the Quotation."))
