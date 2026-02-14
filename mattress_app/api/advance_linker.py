import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry


def validateAndLinkReferences(doc, method=None):
	"""
	Triggered on 'before_insert' of the Advance DocType.
	Automatically finds missing references based on existing data.
	"""
	# 1. If we only have a Quotation, check if an active Sales Order exists
	if doc.quotation_reference and not doc.sale_order_reference:
		so_name = frappe.db.get_value(
			"Sales Order Item", {"prevdoc_docname": doc.quotation_reference, "docstatus": ["<", 2]}, "parent"
		)
		if so_name:
			doc.sale_order_reference = so_name

	# 2. If we only have a Sales Order, find its source Quotation
	elif doc.sale_order_reference and not doc.quotation_reference:
		quo_name = frappe.db.get_value(
			"Sales Order Item", {"parent": doc.sale_order_reference, "docstatus": ["<", 2]}, "prevdoc_docname"
		)
		if quo_name:
			doc.quotation_reference = quo_name


def processNewAdvance(doc, method=None):
	"""
	Triggered after the Advance is saved.
	Passes the entry to another function for further processing.
	"""
	# ADD THIS CHECK:
	# If the advance record was created from a Payment Entry,
	# do NOT trigger the creation of another one.
	if doc.payment_reference_number:
		return
	if doc:
		if doc.sale_order_reference:
			so_doc = frappe.get_doc("Sales Order", doc.sale_order_reference)
			if so_doc.docstatus == 1:
				new_pe_name = createNewPaymentEntry(doc.sale_order_reference, doc)
				doc.db_set("payment_reference_number", new_pe_name)


def getAdvanceDocFromSaleOrder(doc):
	quotation_id = None

	for item in doc.items:
		if hasattr(item, "prevdoc_docname") and item.prevdoc_docname:
			# Check if this ID belongs to a Quotation
			if frappe.db.exists("Quotation", item.prevdoc_docname):
				quotation_id = item.prevdoc_docname
				break

	if not quotation_id:
		# No quotation linked; stop execution
		return

	# 2. Get all Advances linked to this Quotation that don't have an SO link yet
	advances = frappe.get_all(
		"Advance",
		filters={
			"quotation_reference": quotation_id,
		},
		pluck="name",
	)
	return advances


def createOrUpdatePendingPaymentEntry(doc, method=None):
	advances = getAdvanceDocFromSaleOrder(doc)
	if not advances:
		return
	doc.db_set("advance_paid", 0)
	for adv in advances:
		adv_doc = frappe.get_doc("Advance", adv)
		try:
			new_pe_name = None
			should_amend = False

			if adv_doc.payment_reference_number and frappe.db.exists(
				"Payment Entry", adv_doc.payment_reference_number
			):
				old_pe = frappe.get_doc("Payment Entry", adv_doc.payment_reference_number)

				# Check if this PE is already linked to another ACTIVE Sales Order
				active_so_links = []
				for ref in old_pe.references:
					if ref.reference_doctype == "Sales Order":
						so_status = frappe.db.get_value("Sales Order", ref.reference_name, "docstatus")
						# If linked to a Draft (0) or Submitted (1) SO that isn't the current one
						if so_status != 2 and ref.reference_name != doc.name:
							active_so_links.append(ref.reference_name)

				# Decision: Amend only if no other active SOs are linked
				if not active_so_links:
					should_amend = True

			if should_amend:
				# --- CANCEL AND AMEND ---
				old_pe = frappe.get_doc("Payment Entry", adv_doc.payment_reference_number)
				if old_pe.docstatus == 1:
					old_pe.cancel()

				new_pe = frappe.copy_doc(old_pe)
				new_pe.amended_from = old_pe.name
				new_pe.set("references", [])
				new_pe.append(
					"references",
					{
						"reference_doctype": "Sales Order",
						"reference_name": doc.name,
						"total_amount": doc.grand_total,
						"outstanding_amount": doc.grand_total,
						"allocated_amount": adv_doc.amount,
					},
				)

				new_pe.remarks = (
					f"Re-linked to SO {doc.name} (Previous SO was cancelled). Original: {old_pe.name}"
				)
				new_pe.insert(ignore_permissions=True)
				new_pe.submit()
				new_pe_name = new_pe.name

			else:
				# --- CREATE NEW PAYMENT ENTRY ---
				# This runs if no PE existed OR if the old PE was busy with another order
				if not adv_doc.payment_reference_number:
					new_pe_name = createNewPaymentEntry(doc.name, adv_doc)

			# Update the Advance Tracker

			adv_doc.db_set("sale_order_reference", doc.name)
			adv_doc.db_set("payment_reference_number", new_pe_name)

		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Advance Processing Failure: {adv_doc.name}")


def createNewPaymentEntry(sales_order_name, adv_doc, method=None):
	pe = get_payment_entry("Sales Order", sales_order_name)
	pe.posting_date = adv_doc.date
	pe.mode_of_payment = adv_doc.payment_mode
	pe.paid_amount = adv_doc.amount
	pe.received_amount = adv_doc.amount
	pe.reference_no = adv_doc.name

	if pe.references:
		for ref in pe.references:
			if ref.reference_name == sales_order_name:
				ref.allocated_amount = adv_doc.amount

	pe.insert(ignore_permissions=True)
	pe.submit()
	new_pe_name = pe.name
	return new_pe_name


def UpdateAdvanceWithSalesOrderReference(doc, method=None):
	advances = getAdvanceDocFromSaleOrder(doc)
	if not advances:
		return
	for adv_name in advances:
		adv_doc = frappe.get_doc("Advance", adv_name)
		adv_doc.db_set("sale_order_reference", doc.name)


def handleQuotationAmendmends(doc, methond=None):
	if doc.amended_from:
		old_advances = frappe.get_all(
			"Advance", filters={"quotation_reference": doc.amended_from}, pluck="name"
		)
		for adv_name in old_advances:
			frappe.db.set_value("Advance", adv_name, "quotation_reference", doc.name)
			frappe.msgprint(
				f"Linked {len(old_advances)} Advance records from {doc.amended_from} to this amendment."
			)


@frappe.whitelist()
def updateAdvancePaidSilently(doctype, name, total_advance):
	frappe.db.set_value(doctype, name, "advance_paid", total_advance, update_modified=False)


def handleSoCancellation(doc, method=None):
	advances = getAdvanceDocFromSaleOrder(doc)
	if not advances:
		return
	for adv_name in advances:
		frappe.log_error(
			title="So Cancellation Detected",
			message=f"Processing Advance {adv_name} for Sales Order {doc.name}",
		)

		frappe.db.set_value("Advance", adv_name, "sale_order_reference", None)


@frappe.whitelist()
def syncAdvanceAndPeOnView(docname, doctype):
	updated = False
	so_name = None
	quot_ref = None

	if doctype == "Quotation":
		# Check if Quotation is in "Ordered" state
		status = frappe.db.get_value("Quotation", docname, "status")
		if status != "Ordered":
			return {"updated": False}

		quot_ref = docname
		# Find the Sales Order linked to this Quotation
		so_name = frappe.db.get_value(
			"Sales Order Item", {"prevdoc_docname": docname, "docstatus": 1}, "parent"
		)

	elif doctype == "Sales Order":
		so_name = docname
		# Fetch the Quotation name from the Sales Order Item table
		quot_ref = frappe.db.get_value(
			"Sales Order Item", {"parent": so_name, "docstatus": ["<", 2]}, "prevdoc_docname"
		)

	if not so_name:
		return {"updated": False}

	# Fetch all confirmed Payment Entries for the Sales Order
	payments = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_name": so_name, "docstatus": 1, "reference_doctype": "Sales Order"},
		fields=["parent", "allocated_amount"],
	)
	advances = frappe.get_all(
		"Advance",
		filters={"sale_order_reference": so_name, "payment_reference_number": ["is", "set"]},
		fields=["name", "payment_reference_number"],
	)

	for adv in advances:
		pe_doc = frappe.get_doc("Payment Entry", adv.payment_reference_number)
		if pe_doc.docstatus == 2:
			frappe.db.delete("Advance", {"name": adv.name})
			updated = True

	for p in payments:
		# Create missing Advance records in your tracker
		if not frappe.db.exists("Advance", {"payment_reference_number": p.parent}):
			pe_doc = frappe.get_doc("Payment Entry", p.parent)

			adv = frappe.get_doc(
				{
					"doctype": "Advance",
					"date": pe_doc.posting_date,
					"amount": p.allocated_amount,
					"payment_mode": pe_doc.mode_of_payment,
					"payment_reference_number": pe_doc.name,
					"sale_order_reference": so_name,
					"quotation_reference": quot_ref,  # Populated correctly for both cases
				}
			)
			adv.insert(ignore_permissions=True)
			updated = True

	return {"updated": updated}
