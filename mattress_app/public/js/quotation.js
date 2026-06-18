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
						frappe.call({
							method: "frappe.client.set_value",
							args: {
								doctype: frm.doc.doctype,
								name: frm.doc.name,
								fieldname: "custom_customer_type",
								value: r.customer_type,
							},
							callback: function () {
								frm.doc.custom_customer_type = r.customer_type;
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
			}).addClass("btn-primary");
			frm.add_custom_button(__("WA"), () => {
				generate_whatsapp_link(frm);
			})
				.addClass("btn-success")
				.css({
					border: "1px solid #25D366",
					color: "#25D366",
					"background-color": "white",
				});
		}
		frm.set_query("custom_thickness", "items", function (doc, cdt, cdn) {
			let row = locals[cdt][cdn];
			if (!row.custom_name) {
				return {
					filters: { name: ["=", ""] },
				};
			}
			return {
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
					frm.set_value("tc_name", "T&C Hotel");
				} else {
					frm.set_value("tc_name", "T&C General");
				}
			});
		}
	},
	discount_amount: (frm) => frm.events.delayed_calculate(frm),
	discount_percentage: (frm) => frm.events.delayed_calculate(frm),
	apply_discount_on: (frm) => frm.events.delayed_calculate(frm),

	delayed_calculate: function (frm) {
		if (frm.calculation_timeout) {
			clearTimeout(frm.calculation_timeout);
		}
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

		frm.set_value("custom_non_discount_total", non_discount_total);
		frm.set_value("custom_discount_items_total", discountable_total);
		frm.set_value("custom_other_items_mrp_total", custom_other_items_mrp_total);
		frm.set_value("custom_mattress_items_mrp_total", custom_mattress_items_mrp_total);

		frm.refresh_field("custom_non_discount_total");
		frm.refresh_field("custom_discount_items_total");
		frm.refresh_field("custom_other_items_mrp_total");
		frm.refresh_field("custom_mattress_items_mrp_total");
	},
	custom_submit_advance: function (frm) {
		let pending_rows = (frm.doc.custom_payment_entries || []).filter(
			(row) => !row.payment_entry_ref
		);

		if (pending_rows.length === 0) {
			frappe.msgprint(__("No pending advances to submit."));
			return;
		}

		frappe.confirm(__("Submit all pending advances and create vouchers?"), () => {
			pending_rows.forEach((row) => {
				frm.trigger("create_single_voucher", row);
			});
		});
	},

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

// Cache Item Group lookup by Item Name (collision-safe branch key).
// item_name is shared across thicknesses + old variants, but all rows of a
// given name share the SAME item_group, so branching by group is reliable.
const ITEM_NAME_GROUP_CACHE = {};

// Lock to prevent infinite loops
const VARIANT_LOCK = {};

function calculate_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	// Prevent recursion
	if (VARIANT_LOCK[cdn]) return;

	// We need the custom_name to proceed
	if (!row.custom_name) return;

	// Branch by Item Group (collision-safe). item_name is now shared across
	// thicknesses + old variants, so variant_of by name is unreliable. But all
	// items of a given name share the SAME item_group, so group is reliable.
	if (ITEM_NAME_GROUP_CACHE[row.custom_name] !== undefined) {
		route_by_group(frm, cdt, cdn, row, ITEM_NAME_GROUP_CACHE[row.custom_name]);
	} else {
		frappe.db
			.get_list("Item", {
				filters: { item_name: row.custom_name },
				fields: ["item_group"],
				limit: 1,
			})
			.then((res) => {
				const group = res.length > 0 ? res[0].item_group : null;
				ITEM_NAME_GROUP_CACHE[row.custom_name] = group;
				route_by_group(frm, cdt, cdn, row, group);
			});
	}
}

function route_by_group(frm, cdt, cdn, row, group) {
	// Mattresses live in "Products" -> resolver path.
	// Accessories (and anything else) -> non-variant path.
	if (group === "Products") {
		process_item_type(frm, cdt, cdn, row, true);
	} else {
		handle_non_variant_item(frm, cdt, cdn, row);
	}
}

function process_item_type(frm, cdt, cdn, row, is_mattress) {
	if (is_mattress) {
		if (!row.custom_length || !row.custom_width || !row.custom_thickness) return;

		VARIANT_LOCK[cdn] = true;

		frappe.call({
			method: "mattress_app.api.quotation.get_mattress_variant",
			args: {
				custom_length: row.custom_length,
				custom_width: row.custom_width,
				custom_thickness: row.custom_thickness,
				custom_name: row.custom_name,
				price_list: frm.doc.selling_price_list, // use the quotation's price list
			},
			callback(r) {
				if (r.message && r.message.variant_item) {
					// SUCCESS: item resolved (area item, or snapped fixed-price variant)

					// When the item_code CHANGES (thickness/family change), ERPNext
					// fires get_item_details natively, so the override runs on its
					// own - no manual trigger needed. We only need to MANUALLY
					// refresh when the item_code stays the SAME but the standard
					// (rounded) dimensions change, because ERPNext won't refetch
					// the price for an unchanged item_code.
					// Only AREA-priced items share one item_code across sizes and
					// therefore need a manual price refresh on size change. The
					// resolver tells us via is_area. (Fixed-price items change their
					// item_code with size, so ERPNext refetches natively.)
					const item_code_unchanged = row.item_code === r.message.variant_item;
					const std_dims_changed =
						flt(row.custom_standard_length) !== flt(r.message.selected_length) ||
						flt(row.custom_standard_width) !== flt(r.message.selected_width);
					const need_manual_refresh =
						r.message.is_area && item_code_unchanged && std_dims_changed;

					frappe.model
						.set_value(cdt, cdn, {
							item_code: r.message.variant_item,
							custom_standard_width: r.message.selected_width,
							custom_standard_length: r.message.selected_length,
						})
						.then(() => {
							VARIANT_LOCK[cdn] = false;
							// All sizes of a family+thickness share the SAME item_code,
							// so a size change does NOT auto-trigger ERPNext's price
							// fetch. Trigger it ONLY when a price-relevant change
							// happened, so the get_item_details / apply_price_list
							// override re-runs with the new standard dimensions.
							if (need_manual_refresh) {
								frm.script_manager.trigger("item_code", cdt, cdn);
							}
							sync_non_discount_status(frm, cdt, cdn);
						});
				} else {
					// NOT FOUND: reset item-specific fields but KEEP dimensions
					frappe.model.set_value(cdt, cdn, {
						custom_name: null,
						custom_thickness: null,
						custom_width: null,
						custom_length: null,
					});
					frappe.msgprint({
						message: "No item found for this family, thickness and size.",
						indicator: "red",
					});
					VARIANT_LOCK[cdn] = false;
				}
			},
		});
	} else {
		handle_non_variant_item(frm, cdt, cdn, row);
	}
}

// HANDLE NON VARIANT ITEM
function handle_non_variant_item(frm, cdt, cdn, row) {
	if (!row.custom_name) return;

	// Lock the row to prevent calculate_item re-triggering when we set item_code
	VARIANT_LOCK[cdn] = true;

	frappe.db
		.get_list("Item", {
			filters: { item_name: row.custom_name },
			fields: ["name", "custom_discount_applicable"],
			limit: 1,
		})
		.then((res) => {
			if (res && res.length > 0) {
				frappe.model.set_value(cdt, cdn, {
					item_code: res[0].name,
				});
			}
		})
		.finally(() => {
			VARIANT_LOCK[cdn] = false;
		});
}

// Fallback: Also trigger when the item_code is changed/loaded
function item_code(frm, cdt, cdn) {
	let item = locals[cdt][cdn];

	sync_non_discount_status(frm, cdt, cdn);

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
			frappe.model.set_value(cdt, cdn, "custom_non_discount_item", is_non_discount);
			frm.events.delayed_calculate(frm);
		},
	});
}

function generate_whatsapp_link(frm) {
	const ninety_days_ago = frappe.datetime.add_days(frappe.datetime.nowdate(), -90);
	if (
		!frm.doc.key ||
		!frm.doc.custom_key_creation_time ||
		frm.doc.custom_key_creation_time < ninety_days_ago
	) {
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
		return;
	}

	let phone = frm.doc.contact_mobile;
	phone = phone.replace(/\D/g, "");
	if (!phone) {
		frappe.msgprint(
			__("Please ensure a mobile number is entered in the Contact Mobile field.")
		);
		return;
	}
	if (phone.length === 10) {
		phone = "91" + phone;
	}

	const customer_type = frm.doc.custom_customer_type || "Individual";
	const print_format = customer_type === "Company" ? "Quotation-2" : "Quotation-1";
	const base_url = window.location.origin;

	const pdf_params =
		`?doctype=${encodeURIComponent("Quotation")}` +
		`&name=${encodeURIComponent(frm.doc.name)}` +
		`&key=${encodeURIComponent(frm.doc.key)}` +
		`&format=${encodeURIComponent(print_format)}`;

	const pdf_url = base_url + "/printview" + pdf_params;

	const message =
		`*Hello ${frm.doc.customer_name},*\n\n` +
		`Please find your quotation *${frm.doc.name}*.\n\n` +
		`*Order Pdf Link:*\n${pdf_url}`;

	const url = `https://wa.me/${phone}?text=${encodeURIComponent(message)}`;

	if (navigator.clipboard && window.isSecureContext) {
		navigator.clipboard
			.writeText(url)
			.then(() => {
				frappe.show_alert(
					{
						message: __("Link copied to clipboard!"),
						indicator: "green",
					},
					5
				);
			})
			.catch((err) => {
				show_manual_copy_dialog(url);
			});
	} else {
		show_manual_copy_dialog(url);
	}
}

// Fallback function in case the browser blocks automatic copying
function show_manual_copy_dialog(text) {
	let d = new frappe.ui.Dialog({
		title: __("Copy Link"),
		fields: [
			{
				label: __("Copy the text below:"),
				fieldtype: "Small Text",
				fieldname: "copy_text",
				default: text,
				read_only: 0,
			},
		],
		primary_action_label: __("Done"),
		primary_action() {
			d.hide();
		},
	});
	d.show();
}
