"""
Quotation status tracking - DISPLAY-ONLY design.

Stores the stage in a SEPARATE custom_status field. Never touches the native
`status` field, so ERPNext internals are untouched. The form JS displays
custom_status when set.

Fields:
  custom_advance_received (Check)  - auto-ticks when advance > 0; manual too
  custom_size_confirmed   (Check)  - manual
  custom_revisit_date     (Date)   - manual
  custom_status           (Select) - the derived stage (read-only, shown in list)

    bench --site [site] execute mattress_app.api.setup_quotation_status.run
    bench --site [site] execute mattress_app.api.setup_quotation_status.rollback
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

STATUS_OPTIONS = "\n".join(
	[
		"",
		"Draft",
		"Revisit Pending",
		"Advance Pending",
		"Size Pending",
		"Confirmation Pending",
		"Confirmed",
	]
)

FIELDS = {
	"Quotation": [
		{
			"fieldname": "custom_status_section",
			"fieldtype": "Section Break",
			"insert_after": "title",
		},
		{
			"fieldname": "custom_advance_received",
			"fieldtype": "Check",
			"label": "Advance Received",
			"insert_after": "custom_status_section",
		},
		{
			"fieldname": "custom_status_cb1",
			"fieldtype": "Column Break",
			"insert_after": "custom_advance_received",
		},
		{
			"fieldname": "custom_size_confirmed",
			"fieldtype": "Check",
			"label": "Size Confirmed",
			"insert_after": "custom_status_cb1",
		},
		{
			"fieldname": "custom_status_cb2",
			"fieldtype": "Column Break",
			"insert_after": "custom_size_confirmed",
		},
		{
			"fieldname": "custom_revisit_date",
			"fieldtype": "Date",
			"label": "Revisit Date",
			"insert_after": "custom_status_cb2",
		},
		{
			# custom_status stays in the DB (logic + list view use it) but is
			# HIDDEN on the form - no Stage field, no section label.
			"fieldname": "custom_status",
			"fieldtype": "Select",
			"label": "Stage",
			"options": STATUS_OPTIONS,
			"insert_after": "custom_revisit_date",
			"read_only": 1,
			"hidden": 1,
			"in_standard_filter": 1,
		},
		{
			# closing section break - caps the compact row's height so there's
			# no trailing whitespace below it.
			"fieldname": "custom_status_section_end",
			"fieldtype": "Section Break",
			"insert_after": "custom_status",
		},
	]
}


def run():
	create_custom_fields(FIELDS, ignore_validate=True)

	# Fix existing fields (create_custom_fields won't update ones already there):
	# - remove the section label
	if frappe.db.exists("Custom Field", "Quotation-custom_status_section"):
		frappe.db.set_value(
			"Custom Field", "Quotation-custom_status_section", {"insert_after": "title", "label": ""}
		)
	# - hide the Stage field on the form (kept in DB for logic + list)
	if frappe.db.exists("Custom Field", "Quotation-custom_status"):
		frappe.db.set_value("Custom Field", "Quotation-custom_status", {"hidden": 1, "in_list_view": 0})
	# - ensure the compact one-row order via column breaks + insert_after chain
	_order = [
		("Quotation-custom_advance_received", "custom_status_section"),
		("Quotation-custom_status_cb1", "custom_advance_received"),
		("Quotation-custom_size_confirmed", "custom_status_cb1"),
		("Quotation-custom_status_cb2", "custom_size_confirmed"),
		("Quotation-custom_revisit_date", "custom_status_cb2"),
		("Quotation-custom_status", "custom_revisit_date"),
		("Quotation-custom_status_section_end", "custom_status"),
	]
	for name, after in _order:
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "insert_after", after)

	# remove the OLD single column break if it exists (replaced by cb1/cb2)
	if frappe.db.exists("Custom Field", "Quotation-custom_status_cb"):
		frappe.delete_doc("Custom Field", "Quotation-custom_status_cb")

	frappe.clear_cache(doctype="Quotation")
	frappe.db.commit()
	print("Quotation custom_status fields ready (display-only design).")
	return "Done. Run migrate + clear-cache + restart + hard refresh."


def rollback():
	for n in [
		"Quotation-custom_status_section",
		"Quotation-custom_advance_received",
		"Quotation-custom_size_confirmed",
		"Quotation-custom_status_cb",
		"Quotation-custom_status_cb1",
		"Quotation-custom_status_cb2",
		"Quotation-custom_status_section_end",
		"Quotation-custom_revisit_date",
		"Quotation-custom_status",
	]:
		if frappe.db.exists("Custom Field", n):
			frappe.delete_doc("Custom Field", n)
	frappe.clear_cache(doctype="Quotation")
	frappe.db.commit()
	print("Rolled back.")
	return "Rolled back."
