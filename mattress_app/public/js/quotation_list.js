/* Quotation list indicator - Overdue applies ONLY when status is Revisit Pending */

frappe.listview_settings["Quotation"] = frappe.listview_settings["Quotation"] || {};

frappe.listview_settings["Quotation"].has_indicator_for_draft = true;
frappe.listview_settings["Quotation"].has_indicator_for_cancelled = true;

// Ensure both fields are fetched
frappe.listview_settings["Quotation"].add_fields = (
	frappe.listview_settings["Quotation"].add_fields || []
).concat(["custom_status", "custom_revisit_date"]);

const custom_colors = {
	Draft: "red",
	"Revisit Pending": "orange",
	"Advance Pending": "yellow",
	"Size Pending": "yellow",
	"Confirmation Pending": "blue",
	Confirmed: "green",
	Ordered: "green",
	"Partially Ordered": "yellow",
	Cancelled: "red",
	Lost: "darkgrey",
	Expired: "grey",
	Overdue: "red", // Added Overdue color
};

// Controls the explicit "Status" column

// Controls the primary Document Indicator (next to the Title)
frappe.listview_settings["Quotation"].get_indicator = function (doc) {
	const today = frappe.datetime.get_today();

	// 1. Overdue Check (Highly Specific):
	// If the user manually set it to "Revisit Pending", check if the date has passed.
	if (
		doc.custom_status === "Revisit Pending" &&
		doc.custom_revisit_date &&
		doc.custom_revisit_date < today
	) {
		return [__("Overdue"), "red", "custom_revisit_date,<," + today];
	}

	// 2. Standard Custom Status Check:
	// If it's "Advance Pending", or if it's "Revisit Pending" but NOT overdue yet, show standard.
	if (doc.custom_status) {
		return [
			__(doc.custom_status),
			custom_colors[doc.custom_status] || "gray",
			"custom_status,=," + doc.custom_status,
		];
	}

	// 3. Native Fallback (for empty/standard drafts)
	return [__(doc.status), custom_colors[doc.status] || "grey", "status,=," + doc.status];
};
