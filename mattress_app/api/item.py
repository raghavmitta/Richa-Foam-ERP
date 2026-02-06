import frappe


def create_item_name_doc(doc, method):
	# frappe.msgprint("method call")
	# Only for variants
	if not doc.variant_of:
		return

	# Prevent duplicate entry
	if frappe.db.exists("Item Name", {"item_name": doc.item_name}):
		return

	item_name_doc = frappe.new_doc("Item Name")
	item_name_doc.item_name = doc.item_name
	item_name_doc.insert(ignore_permissions=True)


def cleanup_item_name_doc(doc, method):
	# Get the name of the item being deleted
	deleted_item_name = doc.item_name

	# Check if any other items still exist with this name
	remaining_items_count = frappe.db.count("Item", filters={"item_name": deleted_item_name})

	if remaining_items_count == 0:
		# No other variants exist with this name, safe to delete from custom doctype
		# Replace 'Custom Item Name Holder' with your actual Doctype name
		frappe.db.delete("Custom Item Name Holder", {"unique_item_name": deleted_item_name})

		# Optional: Log the deletion
		# frappe.msgprint(f"Last variant deleted. Removed {deleted_item_name} from registry.")


def remove_description(doc, method):
	doc.description = ""
