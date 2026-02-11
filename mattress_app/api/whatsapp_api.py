import hashlib
import os

import frappe
from erpnext.stock.get_item_details import get_price_list_rate
from frappe import _, _dict
from frappe.utils import flt
from frappe.utils.pdf import get_pdf


###############WHATSAPP API#####################
def generate_public_key(doc, method=None):
	"""
	Generates a 16-character secret key if it doesn't exist.
	Hook this to Quotation, Sales Order, and Purchase Order.
	"""
	if not doc.get("key"):
		doc.key = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
	if not doc.get("custom_key_creation_time"):
		doc.custom_key_creation_time = frappe.utils.nowdate()


@frappe.whitelist(allow_guest=True)
def get_public_print_link(doctype, name):
	# Fetch the custom fields you created
	doc_data = frappe.db.get_value(doctype, name, ["key", "custom_key_creation_time"], as_dict=True)
	current_date = frappe.utils.now_datetime().date()
	# Check if we need to rotate the key
	needs_new_key = False
	if not doc_data.custom_public_key or not doc_data.custom_key_creation_time:
		needs_new_key = True
	elif frappe.utils.date_diff(current_date, doc_data.custom_key_creation_time) > 30:
		needs_new_key = True

	public_key = doc_data.custom_public_key

	if needs_new_key:
		# Generating a NEW hash makes the OLD URL 'key' match fail
		public_key = frappe.generate_hash(length=16)
		frappe.db.set_value(
			doctype,
			name,
			{"key": public_key, "custom_key_creation_time": current_date},
			update_modified=False,
		)
		frappe.db.commit()

	doc = frappe.get_doc(doctype, name)
	customer_type = frappe.db.get_value("Customer", doc, "customer_type")

	if customer_type == "Individual":
		print_format = "Quotation-1"
	elif customer_type == "Company":
		print_format = "Quotation-2"

	base_url = frappe.utils.get_url()
	return f"{base_url}/printview?doctype={doctype}&name={name}&key={public_key}&format={print_format}"


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
