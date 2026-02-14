/* global mattress_app */
frappe.ui.form.on("Quotation Item", {
	custom_length: (frm, cdt, cdn) => calculate_item(frm, cdt, cdn),
	custom_width: (frm, cdt, cdn) => calculate_item(frm, cdt, cdn),
	custom_thickness: (frm, cdt, cdn) => calculate_item(frm, cdt, cdn),
	custom_name: (frm, cdt, cdn) => calculate_item(frm, cdt, cdn),
	item_code(frm, cdt, cdn) {
		item_code(frm, cdt, cdn);
	},
	rate: (frm) => frm.events.delayed_calculate(frm),
	qty: (frm) => frm.events.delayed_calculate(frm),
	price_list_rate: (frm) => frm.events.delayed_calculate(frm),
	discount_amount: (frm) => frm.events.delayed_calculate(frm),
	discount_percentage: (frm) => frm.events.delayed_calculate(frm),
});

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (!frm.is_new()) {
			mattress_app.utils.render_advance_tracker(frm);
			if (frm.doc.party_name && !frm.doc.custom_customer_type) {
				frappe.db.get_value("Customer", frm.doc.party_name, "customer_type", (r) => {
					if (r && r.customer_type) {
						// Use db_set to update the database directly without making the form "dirty"
						frappe.call({
							method: "frappe.client.set_value",
							args: {
								doctype: frm.doc.doctype,
								name: frm.doc.name,
								fieldname: "custom_customer_type",
								value: r.customer_type,
							},
							callback: function () {
								// Update the local doc value so the WhatsApp button can see it immediately
								frm.doc.custom_customer_type = r.customer_type;
								// Optionally refresh just the field, not the whole page
								frm.refresh_field("custom_customer_type");
							},
						});
					}
				});
			}
		}

		if (!frm.is_new() && frm.doc.docstatus === 1) {
			frappe.call({
				method: "mattress_app.api.advance_linker.syncAdvanceAndPeOnView",
				args: {
					docname: frm.doc.name,
					doctype: frm.doctype,
				},
				callback: function (r) {
					if (r.message && r.message.updated) {
						frm.reload_doc();
					}
				},
			});
		}
		if (!frm.is_new() && frm.doc.docstatus !== 2) {
			frm.add_custom_button(__("Record Advance"), function () {
				mattress_app.utils.add_advance_payment(frm);
			}).addClass("btn-primary"); // Makes the button blue and easy to see on a tablet
			frm.add_custom_button(__("WA"), () => {
				generate_whatsapp_link(frm);
			})
				.addClass("btn-success")
				.css({
					border: "1px solid #25D366",
					color: "#25D366", // Official WhatsApp Green
					"background-color": "white",
				});
		}
		frm.set_query("custom_thickness", "items", function (doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			if (!row.custom_name) {
				return {
					filters: { name: ["=", ""] }, // Show nothing if no mattress is selected
				};
			}
			return {
				// Point to the new Python function we will create
				query: "mattress_app.api.item_variant.get_available_thickness",
				filters: {
					item_name: row.custom_name,
				},
			};
		});
	},
	party_name: function (frm) {
		if (frm.doc.party_name) {
			frappe.db.get_value("Customer", frm.doc.party_name, "customer_type", (r) => {
				if (r && r.customer_type === "Company") {
					// Automatically set to 'Hotel' terms for Commercial group
					frm.set_value("tc_name", "T&C Hotel");
				} else {
					// Optional: Set a default for everyone else
					frm.set_value("tc_name", "T&C General");
				}
			});
		}
	},
	discount_amount: (frm) => frm.events.delayed_calculate(frm),
	discount_percentage: (frm) => frm.events.delayed_calculate(frm),
	apply_discount_on: (frm) => frm.events.delayed_calculate(frm),

	// This helper function manages the wait time
	delayed_calculate: function (frm) {
		// Clear existing timeout to reset the clock (Debounce)
		if (frm.calculation_timeout) {
			clearTimeout(frm.calculation_timeout);
		}

		// Wait 600ms for other field fetches (like item_details) to finish
		frm.calculation_timeout = setTimeout(() => {
			frm.events.calculate_custom_totals(frm);
		}, 500);
	},

	calculate_custom_totals: function (frm) {
		let non_discount_total = 0;
		let discountable_total = 0;
		let custom_other_items_mrp_total = 0;
		let custom_mattress_items_mrp_total = 0;

		(frm.doc.items || []).forEach((item) => {
			// flt() is crucial here to handle null/undefined values during the "wait"
			let base_amount = flt(item.amount);
			let mrp_amount = flt(item.price_list_rate) * flt(item.qty);

			if (item.custom_non_discount_item) {
				non_discount_total += base_amount;
				custom_other_items_mrp_total += mrp_amount;
			} else {
				discountable_total += base_amount;
				custom_mattress_items_mrp_total += mrp_amount;
			}
		});

		// Use set_value with the third parameter as '1' if you want to avoid
		// triggering the form's 'on_change' event recursively
		frm.set_value("custom_non_discount_total", non_discount_total);
		frm.set_value("custom_discount_items_total", discountable_total);
		frm.set_value("custom_other_items_mrp_total", custom_other_items_mrp_total);
		frm.set_value("custom_mattress_items_mrp_total", custom_mattress_items_mrp_total);

		frm.refresh_field("custom_non_discount_total");
		frm.refresh_field("custom_discount_items_total");
		frm.refresh_field("custom_other_items_mrp_total");
		frm.refresh_field("custom_mattress_items_mrp_total");
	},
	// This function name MUST match the button's Fieldname
	custom_submit_advance: function (frm) {
		// 1. Get all rows that haven't been submitted
		let pending_rows = (frm.doc.custom_payment_entries || []).filter(
			(row) => !row.payment_entry_ref
		);

		if (pending_rows.length === 0) {
			frappe.msgprint(__("No pending advances to submit."));
			return;
		}

		// 2. Ask for confirmation
		frappe.confirm(__("Submit all pending advances and create vouchers?"), () => {
			pending_rows.forEach((row) => {
				frm.trigger("create_single_voucher", row);
			});
		});
	},

	// Helper function to handle the API call for each row
	create_single_voucher: function (frm, row) {
		frappe.call({
			method: "frappe.client.insert",
			args: {
				doc: {
					doctype: "Payment Entry",
					payment_type: "Receive",
					party_type: "Customer",
					party: frm.doc.customer,
					paid_amount: row.amount,
					received_amount: row.amount,
					mode_of_payment: row.mode_of_payment,
					reference_no: row.transaction_id,
					references: [
						{
							reference_doctype: frm.doc.doctype,
							reference_name: frm.doc.name,
							allocated_amount: row.amount,
						},
					],
				},
			},
			callback: function (r) {
				if (!r.exc) {
					// Update the row in the table
					frappe.model.set_value(
						row.doctype,
						row.name,
						"payment_entry_ref",
						r.message.name
					);
					frm.save();
					frappe.show_alert(__("Voucher {0} created", [r.message.name]), 5);
				}
			},
		});
	},
});

/*************************************************
 * VARIANT HANDLING LOGIC
 *************************************************/

// Cache template lookup by Item Name
const ITEM_NAME_TEMPLATE_CACHE = {};

// Lock to prevent infinite loops
const VARIANT_LOCK = {};

function calculate_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	// Prevent recursion
	if (VARIANT_LOCK[cdn]) return;

	// We need the custom_name (Item Name) to proceed
	if (!row.custom_name) return;

	// Fetch template info (cached)
	if (ITEM_NAME_TEMPLATE_CACHE[row.custom_name] !== undefined) {
		process_item_type(frm, cdt, cdn, row, ITEM_NAME_TEMPLATE_CACHE[row.custom_name]);
	} else {
		// Find if any item with this name is a variant
		frappe.db
			.get_list("Item", {
				filters: { item_name: row.custom_name },
				fields: ["variant_of"],
				limit: 1,
			})
			.then((res) => {
				// If the first item found has a 'variant_of', treat the whole group as variants
				const template_item = res.length > 0 ? res[0].variant_of : null;
				ITEM_NAME_TEMPLATE_CACHE[row.custom_name] = template_item;
				process_item_type(frm, cdt, cdn, row, template_item);
			});
	}
}

function process_item_type(frm, cdt, cdn, row, template_item) {
	if (template_item) {
		if (!row.custom_length || !row.custom_width || !row.custom_thickness) return;

		VARIANT_LOCK[cdn] = true;

		frappe.call({
			method: "mattress_app.api.quotation.get_mattress_variant",
			args: {
				custom_length: row.custom_length,
				custom_width: row.custom_width,
				custom_thickness: row.custom_thickness,
				custom_name: row.custom_name,
			},
			callback(r) {
				if (r.message && r.message.variant_item) {
					// ✅ SUCCESS: Variant found
					frappe.model.set_value(cdt, cdn, {
						item_code: r.message.variant_item,
						custom_standard_width: r.message.selected_width,
						custom_standard_length: r.message.selected_length,
					});

					// Sync discount status and calculate totals
					sync_non_discount_status(frm, cdt, cdn);
				} else {
					// ❌ NOT FOUND: Reset item-specific fields but KEEP dimensions
					frappe.model.set_value(cdt, cdn, {
						custom_name: null,
						custom_thickness: null,
						custom_width: null,
						custom_length: null,
					});

					// Inform the user so they know to change dimensions
					frappe.msgprint({
						message: "⚠️ No variant for these standard dimensions.",
						indicator: "red",
					});
				}

				VARIANT_LOCK[cdn] = false;
			},
		});
	} else {
		handle_non_variant_item(frm, cdt, cdn, row);
	}
}

// HANDLE NON VARIANT ITEM
function handle_non_variant_item(frm, cdt, cdn, row) {
	if (!row.custom_name) return;

	// 1. Lock the row to prevent calculate_item from re-triggering
	// when we set the item_code below
	VARIANT_LOCK[cdn] = true;

	frappe.db
		.get_list("Item", {
			filters: { item_name: row.custom_name },
			fields: ["name", "custom_discount_applicable"], // In ERPNext, the 'name' field IS the item_code
			limit: 1,
		})
		.then((res) => {
			if (res && res.length > 0) {
				// 2. Set the Item Code and clear any old standard dimensions
				frappe.model.set_value(cdt, cdn, {
					item_code: res[0].name,
				});
			}
		})
		.finally(() => {
			// 3. IMPORTANT: Unlock only AFTER the DB call and set_value are finished
			VARIANT_LOCK[cdn] = false;
		});
}

// Fallback: Also trigger when the item_code is changed/loaded
function item_code(frm, cdt, cdn) {
	let item = locals[cdt][cdn];

	// 1. First, fetch the discount status from the server
	// We will move the total calculation INSIDE the callback of this function
	sync_non_discount_status(frm, cdt, cdn);

	// 2. Only handle the price sync here
	setTimeout(() => {
		if (item.price_list_rate) {
			frappe.model.set_value(cdt, cdn, "custom_item_price_rate", item.price_list_rate);
		}
	}, 500);
}

function sync_non_discount_status(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;

	frappe.call({
		method: "mattress_app.api.quotation.is_non_discount_item",
		args: { item_code: row.item_code },
		callback: function (r) {
			const is_non_discount = r.message;

			// 1. Set the checkbox
			frappe.model.set_value(cdt, cdn, "custom_non_discount_item", is_non_discount);

			// 3. NOW trigger the calculation (Data is ready!)
			frm.events.delayed_calculate(frm);
		},
	});
}

function generate_whatsapp_link(frm) {
	// Show a loading state for the tablet/mobile users
	if (!frm.doc.key || !frm.doc.custom_key_creation_time) {
		frappe.dom.freeze(__("Refreshing Security Key..."));
		frappe.call({
			method: "mattress_app.api.whatsapp_api.generate_public_key",
			args: {
				doc: frm.doc.name,
				method: null,
			},
			callback: function () {
				frappe.dom.unfreeze();
				frm.reload_doc();
			},
		});
		return; // Wait for the reload to finish before proceeding
	}
	// 2. Add a visual "Loading" freeze so the user doesn't click twice on a slow tablet

	// Handle Phone Number (Checking multiple fields just in case)
	let phone = frm.doc.contact_mobile;
	phone = phone.replace(/\D/g, "");
	if (!phone) {
		frappe.msgprint(
			__("Please ensure a mobile number is entered in the Contact Mobile field.")
		);
		return;
	}

	let customer_type = frm.doc.custom_customer_type || "Individual";

	let print_format = customer_type === "Company" ? "Quotation-2" : "Quotation-1";
	const base_url = `https://richafoam.m.frappe.cloud`;
	let pdf_url = `${base_url}/printview?doctype=${frm.doc.doctype}&name=${frm.doc.name}&key=${frm.doc.key}&format=${print_format}`;

	let message =
		`*Hello ${frm.doc.customer_name},*\n\n` +
		`Please find your quotation *${frm.doc.name}* attached below.\n\n` +
		`*Total:* ${format_currency(frm.doc.rounded_total, frm.doc.currency)}\n\n` +
		`*Order Pdf Link:*\n${pdf_url}\n\n` +
		`Regards,\n${frm.doc.company}`;

	// Open WhatsApp in a new tab
	let url = `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}
