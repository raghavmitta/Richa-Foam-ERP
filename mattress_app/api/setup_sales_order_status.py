"""
Sales Order order-stage setup (display-only over native status, like Quotation).

Creates:
  custom_status      (Select) on Sales Order - the displayed stage. Holds:
                     In Production / Ready for Dispatch / Partially Delivered /
                     Delivered. Staff manually pick 'Ready for Dispatch'; the
                     rest are computed.
  custom_delivered   (Check)  on Sales Order Item - per-item delivered tick.

Also EXTENDS the native Sales Order status options with 'Ready for Dispatch'
so it can be picked (we don't change native backend logic - display only).

    bench --site [site] execute mattress_app.api.setup_sales_order_status.run
    bench --site [site] execute mattress_app.api.setup_sales_order_status.rollback
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

STAGE_OPTIONS = "\n".join(
	[
		"",
		# native values (so custom_status can hold them too, Quotation-style)
		"Draft",
		"To Deliver and Bill",
		"To Bill",
		"To Deliver",
		"Completed",
		"Cancelled",
		"Closed",
		"On Hold",
		# custom stage values
		"In Production",
		"Ready for Dispatch",
		"Partially Delivered",
		"Delivered",
	]
)

FIELDS = {
	"Sales Order": [
		{
			# Hidden Data field - holds the computed stage (set by code only, so
			# no Select options needed and no value-validation errors on save).
			"fieldname": "custom_status",
			"fieldtype": "Data",
			"label": "Order Stage",
			"insert_after": "status",
			"hidden": 1,
			"in_standard_filter": 1,
			"allow_on_submit": 1,
		},
	],
	"Sales Order Item": [
		{
			"fieldname": "custom_delivered",
			"fieldtype": "Check",
			"label": "Delivered",
			"insert_after": "item_code",
			"allow_on_submit": 1,
			"in_list_view": 1,
		},
	],
}


def run():
	create_custom_fields(FIELDS, ignore_validate=True)
	frappe.clear_cache(doctype="Sales Order")
	frappe.db.commit()
	print("Sales Order stage setup complete.")
	return "Done. Run migrate + clear-cache + restart + hard refresh."


def rollback():
	for n in [
		"Sales Order-custom_status",
		"Sales Order Item-custom_delivered",
	]:
		if frappe.db.exists("Custom Field", n):
			frappe.delete_doc("Custom Field", n)
	ps = frappe.db.get_value(
		"Property Setter", {"doc_type": "Sales Order", "field_name": "status", "property": "options"}, "name"
	)
	if ps:
		frappe.delete_doc("Property Setter", ps)
	frappe.clear_cache(doctype="Sales Order")
	frappe.db.commit()
	print("Rolled back Sales Order stage setup.")
	return "Rolled back."
