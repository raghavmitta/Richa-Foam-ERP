/* Sales Order list view - show the order stage (custom_status), falling back
 * to native status when blank (old flow for existing/untouched orders).
 *
 * Place at mattress_app/public/js/sales_order_list.js
 * Wire: doctype_list_js = {"Sales Order": "public/js/sales_order_list.js"}
 */

frappe.listview_settings["Sales Order"] = frappe.listview_settings["Sales Order"] || {};

// Let our indicator/formatter run for draft & cancelled rows too.
frappe.listview_settings["Sales Order"].has_indicator_for_draft = true;
frappe.listview_settings["Sales Order"].has_indicator_for_cancelled = true;

frappe.listview_settings["Sales Order"].add_fields = (
	frappe.listview_settings["Sales Order"].add_fields || []
).concat(["custom_status", "status", "delivery_date", "docstatus"]); // Ensure both fields are fetched

const _SO_STAGE_COLORS = {
	"In Production": "orange",
	"Ready for Dispatch": "blue",
	"Partially Delivered": "yellow",
	Delivered: "green",
	"Due Today": "blue",
	Overdue: "red",
	"Payment Pending": "orange",
};

// Native status colors (fallback) - ERPNext defaults.
const _SO_NATIVE_COLORS = {
	Draft: "red",
	"To Deliver and Bill": "orange",
	"To Bill": "orange",
	"To Deliver": "orange",
	Completed: "green",
	Cancelled: "red",
	Closed: "green",
	"On Hold": "yellow",
};

frappe.listview_settings["Sales Order"].get_indicator = function (doc) {
	const today = frappe.datetime.get_today();
	let s = doc.custom_status;
	if (["In Production", "Ready for Dispatch", "Partially Delivered"].includes(doc.status)) {
		if (doc.delivery_date < today) {
			s = "Overdue";
		}
		if (doc.delivery_date === today) {
			s = "Due Today";
		}
	}
	if (s) {
		return [
			__(s),
			_SO_STAGE_COLORS[s] || _SO_NATIVE_COLORS[doc.status] || "gray",
			"custom_status,=," + s,
		];
	}
	// Fallback to native status.
	return [__(doc.status), _SO_NATIVE_COLORS[doc.status] || "gray", "status,=," + doc.status];
};
