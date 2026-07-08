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
	def declare_enquiry_lost(self, lost_reasons_list, competitors, detailed_reason=None):
		# Signature matches ERPNext exactly:
		#   (self, lost_reasons_list, competitors, detailed_reason=None)
		result = super().declare_enquiry_lost(lost_reasons_list, competitors, detailed_reason)
		# Sync our display field so it is not left stale.
		self.db_set("custom_status", "Lost", update_modified=False)
		return result
