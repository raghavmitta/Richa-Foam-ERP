"""
Add custom_delivered checkbox to Quotation Item (accessories taken at visit).

    bench --site [site] execute mattress_app.api.setup_quotation_item_delivered.run
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Quotation Item": [
		{
			"fieldname": "custom_delivered",
			"fieldtype": "Check",
			"label": "Delivered",
			"insert_after": "item_code",
			"allow_on_submit": 1,
			"in_list_view": 1,
			"description": "Tick if this item was handed to the customer at the "
			"visit (e.g. accessories taken before order is sized).",
		},
	],
}


def run():
	create_custom_fields(FIELDS, ignore_validate=True)
	# ensure properties on an existing field
	if frappe.db.exists("Custom Field", "Quotation Item-custom_delivered"):
		frappe.db.set_value(
			"Custom Field",
			"Quotation Item-custom_delivered",
			{
				"allow_on_submit": 1,
				"in_list_view": 1,
				"insert_after": "item_code",
			},
		)
	frappe.clear_cache(doctype="Quotation Item")
	frappe.db.commit()
	print("Quotation Item custom_delivered ready.")
	return "Done."


def rollback():
	if frappe.db.exists("Custom Field", "Quotation Item-custom_delivered"):
		frappe.delete_doc("Custom Field", "Quotation Item-custom_delivered")
	frappe.clear_cache(doctype="Quotation Item")
	frappe.db.commit()
	return "Rolled back."
