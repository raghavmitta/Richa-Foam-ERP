/* Quotation confirmation popup - ADD to the Quotation form handlers in
 * quotation.js (inside frappe.ui.form.on("Quotation", { ... })).
 *
 * Behaviour:
 *  - When BOTH custom_advance_received AND custom_size_confirmed are ticked,
 *    the FIRST time the user saves, show "Is this order confirmed?".
 *      Yes -> submit the quotation (server sets status = Confirmed)
 *      No  -> save as draft  (server sets status = Confirmation Pending)
 *  - "First time" = status is not already Confirmation Pending / Confirmed.
 */

// Add this key inside frappe.ui.form.on("Quotation", { ... }):
//
//   before_save(frm) {
//       return maybe_confirm_order(frm);
//   },
//
// and define the helper below at file scope.

function maybe_confirm_order(frm) {
	const adv = frm.doc.custom_advance_received;
	const size = frm.doc.custom_size_confirmed;
	const already = ["Confirmation Pending", "Confirmed"].includes(frm.doc.custom_status);

	// Only when both ticked, in draft, and not already past this point.
	if (!adv || !size || frm.doc.docstatus !== 0 || already) {
		return;
	}
	// Guard so we don't loop when we programmatically save/submit below.
	if (frm.__confirm_popup_shown) {
		return;
	}
	frm.__confirm_popup_shown = true;

	// Returning a promise from before_save pauses the save until it resolves.
	return new Promise((resolve) => {
		frappe.confirm(
			__("Is this order confirmed?"),
			() => {
				// YES -> submit (server will mark Confirmed)
				frappe.validated = false; // cancel the in-progress plain save
				frm.savesubmit().always(() => {
					frm.__confirm_popup_shown = false;
				});
				resolve();
			},
			() => {
				// NO -> let the normal save proceed (status -> Confirmation Pending)
				frm.__confirm_popup_shown = false;
				resolve();
			}
		);
	});
}
