# Copyright (c) 2025, Hitc and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class ItemName(Document):
	def on_submit(self):
		self.create_item()

	def create_item(self):
		pass
