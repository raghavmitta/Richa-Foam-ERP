import frappe


def create_item_name_doc(doc, method):
	# frappe.msgprint("method call")
	# Only for variants
	if doc.has_variants:
		return

	# Prevent duplicate entry
	if frappe.db.exists("Item Name", {"item_name": doc.item_name}):
		return

	item_name_doc = frappe.new_doc("Item Name")
	item_name_doc.item_name = doc.item_name
	item_name_doc.insert(ignore_permissions=True)


def cleanup_item_name_doc(doc, method):
	# 1. Get and clean the name
	target_name = doc.item_name.strip() if doc.item_name else None

	if not target_name:
		return

	# This checks for existing variants only.
	other_variant_exists = frappe.db.exists(
		"Item",
		{
			"item_name": target_name,
			"name": ["!=", doc.name],
			"has_variants": 0,  # Only look for items that are NOT templates
		},
	)

	if not other_variant_exists:
		# 3. If no other variants exist, delete from 'Item Name' DocType
		if frappe.db.exists("Item Name", target_name):
			try:
				frappe.delete_doc("Item Name", target_name, ignore_permissions=True)
				frappe.msgprint(
					msg=f"<b>Updated:</b> All variants for '{target_name}' are gone.",
					title=("Cleanup Successful"),
					indicator="green",
				)
			except frappe.LinkExistsError:
				frappe.msgprint(f"Could not delete '{target_name}' it is linked to other records.")
