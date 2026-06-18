import frappe


def sync_thickness_from_item_attribute(doc, method):
	# Only act if this attribute is marked as Thickness
	if not doc.custom_is_thickness:
		return

	for row in doc.item_attribute_values:
		if not row.attribute_value:
			continue

		sync_thickness_delete_row(doc)
		# Check if Thickness already exists
		thickness_name = frappe.db.exists("Thickness", {"reference": doc.name, "value": row.attribute_value})

		if thickness_name:
			# Update abbr if changed
			frappe.db.set_value("Thickness", thickness_name, "abbr", row.abbr)
		else:
			# Create Thickness record
			frappe.get_doc(
				{
					"doctype": "Thickness",
					"value": row.attribute_value,
					"abbr": row.abbr,
					"reference": doc.name,
				}
			).insert(ignore_permissions=True)


def sync_thickness_delete(doc, method):
	if not doc.custom_is_thickness:
		return

	old_doc = frappe.get_doc("Item Attribute", doc.name)

	old_values = {row.attribute_value for row in old_doc.item_attribute_values}
	new_values = {row.attribute_value for row in doc.item_attribute_values}

	removed_values = old_values - new_values

	for value in removed_values:
		in_use = frappe.db.exists("Item Variant Attribute", {"attribute": doc.name, "attribute_value": value})

		if in_use:
			frappe.throw(f"Cannot remove thickness {value}. It is used in Item Variants.")

		thickness_doc = frappe.db.get_value("Thickness", {"reference": doc.name, "value": value}, "name")

		if thickness_doc:
			frappe.delete_doc("Thickness", thickness_doc, ignore_permissions=True)


def sync_thickness_delete_row(doc):
	if not doc.custom_is_thickness:
		return

	# Get current values AFTER save
	current_values = {row.attribute_value for row in doc.item_attribute_values}

	# Get all Thickness records linked to this attribute
	thickness_records = frappe.db.get_all(
		"Thickness", filters={"reference": doc.name}, fields=["name", "value"]
	)

	for t in thickness_records:
		if t.value not in current_values:
			# Safety: check if used by any variant
			in_use = frappe.db.exists(
				"Item Variant Attribute", {"attribute": doc.name, "attribute_value": t.value}
			)

			if in_use:
				frappe.throw(f"Cannot remove thickness {t.value}. It is used in Item Variants.")

			frappe.delete_doc("Thickness", t.name, ignore_permissions=True)


@frappe.whitelist()
def get_available_thickness(doctype, txt, searchfield, start, page_len, filters):
	item_name = filters.get("item_name")
	values = set()

	# 1) NEW area items via the custom_thickness_link field
	rows = frappe.get_all(
		"Item",
		filters={"item_name": item_name, "custom_thickness_link": ["is", "set"]},
		fields=["custom_thickness_link"],
	)
	thk_names = {r["custom_thickness_link"] for r in rows if r.get("custom_thickness_link")}
	for thk_name in thk_names:
		val = frappe.db.get_value("Thickness", thk_name, "value")
		if val is not None:
			values.add(str(val).strip())

	# 2) OLD variants: thickness attribute values among this family's variants
	old = frappe.db.sql(
		"""
		SELECT DISTINCT attribute_value
		FROM `tabItem Variant Attribute`
		WHERE variant_of = %s AND attribute = 'Thickness mm'
		""",
		(item_name,),
	)
	for (val,) in old:
		if val is not None:
			values.add(str(val).strip())

	# 3) Fallback ONLY if nothing found at all
	if not values:
		raw_list = frappe.get_list("Thickness", pluck="value")
		values = {str(v).strip() for v in raw_list if v is not None}

	def _key(v):
		try:
			return (0, float(v))
		except (TypeError, ValueError):
			return (1, v)

	return [[f"{v}MM"] for v in sorted(values, key=_key)]
