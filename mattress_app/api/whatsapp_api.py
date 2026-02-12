import hashlib
import os

import frappe
from erpnext.stock.get_item_details import get_price_list_rate
from frappe import _, _dict
from frappe.utils import flt
from frappe.utils.pdf import get_pdf


###############WHATSAPP API#####################
@frappe.whitelist()
def generate_public_key(doc, method=None):
	"""
	Generates a 16-character secret key if it doesn't exist.
	Hook this to Quotation, Sales Order, and Purchase Order.
	"""
	current_date = frappe.utils.now_datetime().date()
	needs_new_key = False
	is_manual_call = False
	if isinstance(doc, str):
		doc = frappe.get_doc("Quotation", doc)
		is_manual_call = True

	if not is_manual_call:
		if not doc.get("key") or not doc.get("custom_key_creation_time"):
			needs_new_key = True
		elif frappe.utils.date_diff(current_date, doc.get("custom_key_creation_time")) > 90:
			needs_new_key = True
		if needs_new_key:
			doc.key = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
			doc.custom_key_creation_time = frappe.utils.nowdate()
	if is_manual_call:
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def validate_public_key_expiry(doc, method=None, *args, **kwargs):
	# ONLY apply restrictions to outsiders (Guests)
	if frappe.session.user == "Guest":
		dt = frappe.request.args.get("doctype")  # e.g., 'Sales Order'
		dn = frappe.request.args.get("name")  # e.g., 'SAL-ORD-2026-00027'
		provided_key = frappe.request.args.get("key")
		if not dt or not dn:
			frappe.throw("Invalid Request: Missing document parameters.")
		db_data = frappe.db.get_value(dt, dn, ["key", "custom_key_creation_time"], as_dict=True)
		# 4. Security Gate: Compare the Keys
		if not db_data or not provided_key or provided_key != db_data.get("key"):
			frappe.throw(
				msg="Access Denied: A valid secure key is required to view this document.",
				title="Unauthorized",
				exc=frappe.PermissionError,
			)

		# 5. Expiry Gate: Check the 30-day window
		if db_data.get("custom_key_creation_time"):
			days_passed = frappe.utils.date_diff(
				frappe.utils.nowdate(), db_data.get("custom_key_creation_time")
			)
			if days_passed > 90:
				frappe.throw(
					msg="This secure link has expired. Please request a new one.",
					title="Link Expired",
					exc=frappe.PermissionError,
				)
