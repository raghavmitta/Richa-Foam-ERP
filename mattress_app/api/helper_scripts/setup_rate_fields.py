"""
Phase B1 (setup) : Add pricing-control fields to the Item doctype.

Creates THREE things on Item:
  1. custom_use_area_pricing (Check)  - the flow switch:
        ticked  -> product uses NEW calculated-rate flow
        unticked-> product uses OLD fixed-price flow (Magniflex, pillows, etc.)
  2. custom_mattress_pricing_section (Section Break) - groups the fields
  3. custom_thickness_prices (Table -> Item Thickness Price) - per-thickness rate,
     only relevant when area pricing is on.

Run once on each site:
    bench --site [site] execute mattress_app.api.setup_rate_fields.run
    bench --site [site] migrate

Reversible:
    bench --site [site] execute mattress_app.api.setup_rate_fields.rollback
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def run():
	fields = {
		"Item": [
			{
				"fieldname": "custom_mattress_pricing_section",
				"fieldtype": "Section Break",
				"label": "Mattress Pricing",
				"insert_after": "description",
				"collapsible": 1,
			},
			{
				"fieldname": "custom_use_area_pricing",
				"fieldtype": "Check",
				"label": "Calculate Price from Area",
				"insert_after": "custom_mattress_pricing_section",
				"description": (
					"Controls PRICE ONLY (not the variant flow). "
					"Ticked: price is calculated = rate x length x width (foam mattresses). "
					"Unticked: price comes from the variant's own Item Price "
					"(Magniflex keeps its variant flow but uses its own per-size prices; "
					"pillows/protectors/accessories use their fixed price)."
				),
			},
			{
				"fieldname": "custom_thickness_link",
				"fieldtype": "Link",
				"label": "Thickness",
				"options": "Thickness",
				"insert_after": "custom_use_area_pricing",
				"depends_on": "eval:doc.custom_use_area_pricing==1",
				"description": "Thickness of this area-priced item. Used to populate the thickness dropdown on quotations.",
			},
		]
	}
	create_custom_fields(fields, ignore_validate=True)
	frappe.db.commit()
	msg = "Phase B1 setup complete: custom_use_area_pricing flag added to Item (rate lives in Item Price)."
	print(msg)
	return msg


def rollback():
	for name in [
		"Item-custom_use_area_pricing",
		"Item-custom_thickness_link",
		"Item-custom_mattress_pricing_section",
	]:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
	frappe.db.commit()
	return "Rolled back pricing custom fields."
