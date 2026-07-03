"""
Minimal Quotation class override - ONLY to sync custom_status when a quotation
is marked Lost via 'declare_enquiry_lost' (which uses db_set and bypasses the
validate/on_update hooks).

Wire in hooks.py:
    override_doctype_class = {
        "Quotation": "mattress_app.api.quotation_override.CustomQuotation",
    }

This does NOT reimplement any status logic - it just calls ERPNext's original
method, then sets custom_status = 'Lost'. Low risk.
"""

from erpnext.selling.doctype.quotation.quotation import Quotation


class CustomQuotation(Quotation):
	def declare_enquiry_lost(self, *args, **kwargs):
		# Run ERPNext's original 'mark as lost' logic (sets native status=Lost),
		# passing through whatever args this ERPNext version uses.
		result = super().declare_enquiry_lost(*args, **kwargs)
		# Then sync our display field so it isn't left stale.
		self.db_set("custom_status", "Lost", update_modified=False)
		return result
