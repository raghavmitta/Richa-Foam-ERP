"""
Quotation status logic - ADD these to mattress_app/api/quotation.py
(or keep as a separate module and wire the hooks to this path).

Wire in hooks.py under Quotation:
    "validate":   "...quotation.derive_quotation_status"   (add to existing list)
    "on_submit":  "...quotation.set_confirmed_on_submit"   (add to existing list)

Status decision tree (DRAFT, docstatus 0):
    advance size revisit  -> custom_status
    0       0    empty     -> Draft
    0       0    filled    -> Revisit Pending
    1       0    any       -> Size Pending
    0       1    any       -> Advance Pending
    1       1    any       -> Confirmation Pending
  On SUBMIT (docstatus 1) -> Confirmed (always)
"""

from frappe.utils import flt

# Field holding the advance amount (label "Advance Paid")
ADVANCE_FIELD = "advance_paid"


def derive_quotation_status(doc, method=None):
	"""validate hook: auto-tick advance + derive the draft stage."""
	# 1) Auto-tick advance_received when an advance amount exists.
	#    Only ever turns it ON (never OFF), so a manual tick is preserved.
	if flt(doc.get(ADVANCE_FIELD)) > 0 and not doc.get("custom_advance_received"):
		doc.custom_advance_received = 1

	# 2) Only derive the stage while the quotation is still a DRAFT.
	#    On submit, set_confirmed_on_submit() handles the Confirmed status.
	if doc.docstatus != 0:
		return

	adv = bool(doc.get("custom_advance_received"))
	size = bool(doc.get("custom_size_confirmed"))
	revisit = bool(doc.get("custom_revisit_date"))

	if adv and size:
		doc.custom_status = "Confirmation Pending"
	elif adv and not size:
		doc.custom_status = "Size Pending"
	elif size and not adv:
		doc.custom_status = "Advance Pending"
	elif revisit:
		doc.custom_status = "Revisit Pending"
	else:
		doc.custom_status = "Draft"


def set_confirmed_on_submit(doc, method=None):
	"""on_submit hook: a submitted quotation is always Confirmed."""
	# db_set writes directly and persists without re-triggering validate.
	doc.db_set("custom_status", "Confirmed")
