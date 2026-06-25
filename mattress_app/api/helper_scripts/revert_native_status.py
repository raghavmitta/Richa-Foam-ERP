"""
Revert the native-status override damage and restore ERPNext's native status.

Run AFTER removing from hooks.py:
  - override_doctype_class for Quotation
  - derive_quotation_status / apply_quotation_status / set_confirmed_on_submit

    bench --site [site] execute mattress_app.api.revert_native_status.run
"""

import frappe

OUR_VALUES = [
	"Revisit Pending",
	"Advance Pending",
	"Size Pending",
	"Confirmation Pending",
	"Confirmed",
]


def run():
	# 1) Remove the property setter that injected our values into native status.
	ps = frappe.db.get_value(
		"Property Setter",
		{
			"doc_type": "Quotation",
			"field_name": "status",
			"property": "options",
		},
		"name",
	)
	if ps:
		frappe.delete_doc("Property Setter", ps)
		print("Removed status-options property setter (native options restored).")

	# 2) Restore native status on any Quotation that currently holds one of our
	#    custom values, based on docstatus + linked Sales Order.
	rows = frappe.db.sql(
		"""SELECT name, docstatus FROM `tabQuotation` WHERE status IN ({})""".format(
			", ".join(["%s"] * len(OUR_VALUES))
		),
		OUR_VALUES,
		as_dict=True,
	)
	fixed = 0
	for r in rows:
		if r.docstatus == 2:
			native = "Cancelled"
		elif r.docstatus == 1:
			# Ordered if a submitted SO references this quotation, else Open
			has_so = frappe.db.exists(
				"Sales Order Item",
				{"prevdoc_docname": r.name, "docstatus": ["<", 2]},
			)
			native = "Ordered" if has_so else "Open"
		else:
			native = "Draft"
		frappe.db.set_value("Quotation", r.name, "status", native, update_modified=False)
		fixed += 1

	frappe.db.commit()
	frappe.clear_cache(doctype="Quotation")
	print(f"Restored native status on {fixed} quotations.")
	return "Revert complete."
