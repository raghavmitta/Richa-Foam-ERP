"""
Minimal Quotation class override - ONLY to sync custom_status when a quotation
is marked Lost via 'declare_enquiry_lost' (which uses db_set and bypasses the
validate/on_update hooks).

Wire in hooks.py:
    override_doctype_class = {
        "Quotation": "mattress_app.api.quotation_override.CustomQuotation",
    }
"""

import frappe
from erpnext.selling.doctype.quotation.quotation import Quotation


class CustomQuotation(Quotation):
	@frappe.whitelist()
	def declare_enquiry_lost(self, *args, **kwargs):
		# @frappe.whitelist() is REQUIRED here: overriding a whitelisted parent
		# method without re-applying the decorator drops its whitelist status,
		# and run_doc_method then rejects the call ('not permitted').
		result = super().declare_enquiry_lost(*args, **kwargs)
		# Sync our display field so it isn't left stale.
		self.db_set("custom_status", "Lost", update_modified=False)
		return result
