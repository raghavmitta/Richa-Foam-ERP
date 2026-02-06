import hashlib
import os

import frappe
from erpnext.stock.get_item_details import get_price_list_rate
from frappe import _, _dict
from frappe.utils import flt
from frappe.utils.pdf import get_pdf


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
	    diff <= 0.5 → lower
	    diff > 0.5  → higher
	"""
	standards = sorted(standards)

	# Below minimum
	if custom <= standards[0]:
		return standards[0]

	# Above maximum
	if custom >= standards[-1]:
		return standards[-1]

	for i in range(len(standards) - 1):
		low = standards[i]
		high = standards[i + 1]

		if low <= custom <= high:
			diff = custom - low
			return low if diff <= 0.5 else high

	return standards[-1]


@frappe.whitelist()
def get_mattress_variant(custom_length, custom_width, custom_thickness, custom_name):
	custom_length = float(custom_length)
	custom_width = float(custom_width)
	custom_thickness = frappe.db.get_value("Thickness", custom_thickness, "value")

	standard_lengths = get_attribute_values("Length")
	standard_widths = get_attribute_values("Width")

	selected_length = pick_standard_value(custom_length, standard_lengths)
	selected_width = pick_standard_value(custom_width, standard_widths)

	# Convert float → clean string for varchar match
	len_val = str(int(selected_length)) if float(selected_length).is_integer() else str(selected_length)
	wid_val = str(int(selected_width)) if float(selected_width).is_integer() else str(selected_width)
	thk_val = str(int(float(custom_thickness))) if float(custom_thickness).is_integer() else custom_thickness

	# FIND VARIANT BY item_name + Length + Width + Thickness
	variant_item = frappe.db.sql(
		"""
        SELECT item.name
        FROM `tabItem` item
        INNER JOIN `tabItem Variant Attribute` len_attr
            ON len_attr.parent = item.name
            AND len_attr.attribute = 'Length'
            AND len_attr.attribute_value = %s
        INNER JOIN `tabItem Variant Attribute` wid_attr
            ON wid_attr.parent = item.name
            AND wid_attr.attribute = 'Width'
            AND wid_attr.attribute_value = %s
        INNER JOIN `tabItem Variant Attribute` thk_attr
            ON thk_attr.parent = item.name
            AND thk_attr.attribute = 'Thickness mm'
            AND thk_attr.attribute_value = %s
        WHERE item.item_name = %s
        LIMIT 1
    """,
		(len_val, wid_val, thk_val, custom_name),
		as_dict=True,
	)

	# handle the result
	item_code = variant_item[0].name if variant_item else None
	if item_code:
		if custom_length < custom_width:
			frappe.msgprint("<span style='color:red;'>🚫 Dimensions: </b> Length is less than Width</span>")
		frappe.msgprint(f"""
        <table class="table table-bordered">
            <tr>
                <th>Type</th>
                <th>Thickness (mm)</th>
                <th>Length (inch)</th>
                <th>Width (inch)</th>
            </tr>
            <tr>
                <td><b>Custom</b></td>
                <td>{custom_thickness}</td>
                <td>{custom_length}</td>
                <td>{custom_width}</td>
            </tr>
            <tr>
                <td><b>Standard</b></td>
                <td>{custom_thickness}</td>
                <td>{selected_length}</td>
                <td>{selected_width}</td>
            </tr>
        </table>
        """)

	# if not item_code:
	# frappe.throw(("No matching variant found for these Standard Dimensions."), title="Variant Not Found")

	return {
		"selected_length": selected_length,
		"selected_width": selected_width,
		"selected_thickness": thk_val,
		"variant_item": variant_item[0].name if variant_item else None,
	}


#################RATE LOWER THAN ITEM PRICE WARNING MESSAGE#####################
def rate_lower_warning(doc, method):
	# apply_selective_discount(doc)
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

	# ---------------------------------------
	# STEP 1: Identify discountable items
	# ---------------------------------------
	for item in doc.items:
		discount_flag = frappe.db.get_value("Item", item.item_code, "custom_discount_applicable") or 0

		if discount_flag == 0:
			base_amount = item.amount or 0
			discountable_items.append(item)
			discountable_total += base_amount
		else:
			# NON-DISCOUNTABLE ITEM → FORCE RESTORE
			item.distributed_discount_amount = 0
			item.discount_percentage = 0  # 🔧 REQUIRED

			item.net_amount = item.amount
			item.net_rate = item.rate  # 🔧 SAFE

			# 🔧 REQUIRED BASE FIELDS (GST SAFE)
			item.base_net_amount = item.base_amount
			item.base_net_rate = item.base_rate

			# GST-critical fields
			item.taxable_value = item.net_amount
			item.base_taxable_value = item.base_net_amount

	if not discountable_items:
		doc.discount_amount = 0
		doc.additional_discount_percentage = 0
		return

	# ---------------------------------------
	# STEP 2: Determine total discount
	# ---------------------------------------
	if doc.additional_discount_percentage:
		total_discount = (discountable_total * doc.additional_discount_percentage) / 100
	else:
		total_discount = doc.discount_amount or 0

	if total_discount <= 0:
		return

	if total_discount > discountable_total:
		frappe.throw("Additional discount cannot exceed total of discountable items.")

	# ---------------------------------------
	# STEP 3: Distribute discount
	# ---------------------------------------
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

		# 🔧 REQUIRED BASE FIELDS (GST SAFE)
		item.base_net_amount = item.base_amount - distributed
		item.base_net_rate = item.base_net_amount / item.qty if item.qty else 0

		# GST-critical
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
