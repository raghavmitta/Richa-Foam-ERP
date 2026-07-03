"""
Sales Order order-stage + payment logic.

Computes custom_status (the displayed stage) from native status + per-item
delivered ticks, plus payment state:
  Delivered + balance owing  -> 'Payment Pending'
  Delivered + fully paid     -> auto-close the order (-> 'Closed')

Wire in hooks.py under Sales Order:
    "validate":                "...sales_order.derive_sales_order_status"
    "on_update_after_submit":  "...sales_order.derive_status_after_submit"
    "on_cancel":               [..., "...sales_order.set_so_cancelled_status"]
override_whitelisted_methods:
    "erpnext...sales_order.update_status": "...sales_order.update_status_override"
"""

import frappe
from erpnext.selling.doctype.sales_order.sales_order import (
	update_status as _erpnext_update_status,
)
from frappe.utils import flt

_DISPATCH_STAGES = ("Ready for Dispatch", "Partially Delivered", "Delivered", "Payment Pending")


def _balance_due(doc):
	"""rounded_total - advance_paid (what the customer still owes)."""
	return flt(doc.get("rounded_total")) - flt(doc.get("advance_paid"))


def _maybe_auto_close(docname, native_status, items_total, items_delivered, balance_due):
	"""Auto-close the order when fully delivered AND fully paid.
	Returns True if a close was triggered."""
	if native_status in ("Closed", "Cancelled"):
		return False
	if items_total > 0 and items_delivered >= items_total and balance_due <= 0:
		_erpnext_update_status("Closed", docname)
		frappe.db.set_value("Sales Order", docname, "custom_status", "Closed", update_modified=False)
		return True
	return False


def _compute_so_stage(native_status, manual_stage, items_total, items_delivered, docstatus, balance_due=0):
	"""custom_status holds the displayed stage. Native lifecycle states
	(Cancelled / On Hold / Closed) ALWAYS win over the custom stage.

	balance_due = rounded_total - advance_paid. When fully delivered:
	  balance_due > 0  -> 'Payment Pending'
	  balance_due <= 0 -> 'Delivered' (caller auto-closes the order)."""
	# 1) Native lifecycle states win - checked FIRST.
	if docstatus == 2 or native_status == "Cancelled":
		return "Cancelled"
	if docstatus == 0 or native_status == "Draft":
		return "Draft"
	if native_status in ("On Hold", "Closed"):
		return native_status

	# 2) Delivery ticks drive Partially Delivered / Delivered (no gate).
	if manual_stage in _DISPATCH_STAGES:
		if items_total > 0 and items_delivered >= items_total:
			if balance_due > 0:
				return "Payment Pending"
			return "Delivered"
		if items_delivered > 0:
			return "Partially Delivered"
		return "Ready for Dispatch"

	# 4) Otherwise map the production native status to 'In Production'.
	if native_status == "To Deliver and Bill":
		return "In Production"
	return native_status or ""


def derive_sales_order_status(doc, method=None):
	"""validate hook: set custom_status (the displayed stage) from item ticks."""
	items = doc.get("items") or []
	total = len(items)
	delivered = sum(1 for it in items if it.get("custom_delivered"))
	balance = _balance_due(doc)

	new_stage = _compute_so_stage(
		doc.get("status"), doc.get("custom_status"), total, delivered, doc.docstatus, balance
	)
	if new_stage is not None:
		doc.custom_status = new_stage


def derive_status_after_submit(doc, method=None):
	"""on_update_after_submit hook: submitted-doc edits fire THIS, not validate.
	Recompute custom_status (handles item ticks, payment, On Hold/Closed)."""
	items = doc.get("items") or []
	total = len(items)
	delivered = sum(1 for it in items if it.get("custom_delivered"))
	balance = _balance_due(doc)

	if _maybe_auto_close(doc.name, doc.get("status"), total, delivered, balance):
		return

	new_stage = _compute_so_stage(
		doc.get("status"), doc.get("custom_status"), total, delivered, doc.docstatus, balance
	)
	if new_stage is not None and new_stage != doc.get("custom_status"):
		doc.db_set("custom_status", new_stage, update_modified=False)


def recompute_so_status(docname):
	"""Recompute custom_status by reading item ticks fresh from the DB. Used by
	the button paths (which db_set items, bypassing validate). Auto-closes when
	fully delivered + fully paid."""
	doc = frappe.get_doc("Sales Order", docname)
	total = len(doc.items)
	delivered = sum(1 for it in doc.items if it.get("custom_delivered"))
	balance = _balance_due(doc)

	if _maybe_auto_close(docname, doc.status, total, delivered, balance):
		frappe.db.commit()
		return "Closed"

	new_stage = _compute_so_stage(doc.status, doc.custom_status, total, delivered, doc.docstatus, balance)
	frappe.db.set_value("Sales Order", docname, "custom_status", new_stage, update_modified=False)
	frappe.db.commit()
	return new_stage


@frappe.whitelist()
def mark_all_delivered(docname, delivered=1):
	"""Tick (or untick) custom_delivered on every item, then re-derive."""
	delivered = int(delivered)
	doc = frappe.get_doc("Sales Order", docname)
	for it in doc.items:
		it.db_set("custom_delivered", delivered, update_modified=False)
	frappe.db.commit()
	new_stage = recompute_so_status(docname)
	return {"stage": new_stage}


@frappe.whitelist()
def mark_ready_for_dispatch(docname):
	"""Set the stage to 'Ready for Dispatch' (the manual step)."""
	doc = frappe.get_doc("Sales Order", docname)
	total = len(doc.items)
	delivered = sum(1 for it in doc.items if it.get("custom_delivered"))
	balance = _balance_due(doc)
	new_stage = _compute_so_stage(
		doc.get("status"), "Ready for Dispatch", total, delivered, doc.docstatus, balance
	)
	doc.db_set("custom_status", new_stage, update_modified=False)
	frappe.db.commit()
	return {"stage": new_stage}


def set_so_cancelled_status(doc, method=None):
	"""Sales Order on_cancel hook: set custom_status to Cancelled directly."""
	doc.db_set("custom_status", "Cancelled", update_modified=False)


@frappe.whitelist()
def sync_so_status(docname):
	"""Recompute custom_status from current state + auto-close. Called by the
	update_status override and the advance tracker path."""
	doc = frappe.get_doc("Sales Order", docname)
	total = len(doc.items)
	delivered = sum(1 for it in doc.items if it.get("custom_delivered"))
	balance = _balance_due(doc)

	if _maybe_auto_close(docname, doc.status, total, delivered, balance):
		frappe.db.commit()
		return "Closed"

	new_stage = _compute_so_stage(doc.status, doc.custom_status, total, delivered, doc.docstatus, balance)
	if new_stage != doc.custom_status:
		frappe.db.set_value("Sales Order", docname, "custom_status", new_stage, update_modified=False)
		frappe.db.commit()
	return new_stage


@frappe.whitelist()
def update_status_override(status, name):
	"""Override of ERPNext's update_status (Hold/Close/Resume/Re-open buttons).
	Runs ERPNext's original logic, then syncs custom_status."""
	_erpnext_update_status(status, name)
	sync_so_status(name)


def add_purchase_mobile(doc, method):
	doc.custom_quotation_reference = doc.items[0].prevdoc_docname
	add_sales_person(doc)
	if doc.company:
		purchase_mobile = frappe.db.get_value("Company", doc.company, "custom_purchase_mobile_no")
		if purchase_mobile:
			doc.custom_purchase_mobile = purchase_mobile


def add_sales_person(doc):
	if doc.custom_quotation_reference:
		sales_person = frappe.get_value("Quotation", doc.custom_quotation_reference, "custom_salesman")
		if sales_person:
			doc.set("sales_team", [])
			doc.append("sales_team", {"sales_person": sales_person, "allocated_percentage": 100})
