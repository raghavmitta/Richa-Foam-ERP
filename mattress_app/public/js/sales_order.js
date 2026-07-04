/* global mattress_app */
/* Sales Order client script:
 *  - Advance tracker + Record Advance button (existing)
 *  - Advance/PE sync on view + WA DINESH WhatsApp send (existing)
 *  - Order-stage UI: sync_so_status, transforming button, stage indicator (new)
 *  - Per-item delivered tick -> recompute (new)
 */

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (!frm.is_new()) mattress_app.utils.render_advance_tracker(frm);

		// Record Advance button (drafts + submitted, not cancelled).
		if (!frm.is_new() && frm.doc.docstatus !== 2) {
			frm.add_custom_button(__("Record Advance"), function () {
				mattress_app.utils.add_advance_payment(frm);
			}).addClass("btn-primary");
		}

		// Submitted-only: advance/PE sync on view + WhatsApp button.
		if (!frm.is_new() && frm.doc.docstatus === 1) {
			frappe.call({
				method: "mattress_app.api.advance_linker.syncAdvanceAndPeOnView",
				args: { docname: frm.doc.name, doctype: frm.doctype },
				callback: function (r) {
					if (r.message && r.message.updated) {
						frm.reload_doc();
					}
				},
			});

			frm.add_custom_button(__("WA DINESH"), () => {
				send_whatsapp(frm);
			})
				.addClass("btn-success")
				.css({
					border: "1px solid #25D366",
					color: "#25D366",
					"background-color": "white",
				});
		}

		// Order-stage: sync custom_status (catches Hold/Close/Cancel), then
		// display the indicator. Reload if it drifted.
		if (!frm.is_new()) {
			frappe.call({
				method: "mattress_app.api.sales_order.sync_so_status",
				args: { docname: frm.doc.name },
				callback: function (r) {
					if (r.message && r.message !== frm.doc.custom_status) {
						frm.reload_doc();
						return;
					}
					show_so_stage_indicator(frm);
				},
			});
		} else {
			show_so_stage_indicator(frm);
		}
		add_stage_button(frm);
	},
});

frappe.ui.form.on("Sales Order Item", {
	custom_delivered(frm, cdt, cdn) {
		// Tick in the grid -> save so the server recomputes the stage.
		if (frm.doc.docstatus === 1) {
			frm.save("Update").then(() => frm.reload_doc());
		} else {
			frm.dirty();
		}
	},
});

/* ---------- Order-stage UI ---------- */

function add_stage_button(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 1) return;

	const stage = frm.doc.custom_status;

	// In Production (or blank) -> offer 'Mark Ready for Dispatch'.
	if (!stage || stage === "In Production") {
		frm.add_custom_button(__("Mark Ready for Dispatch"), () => {
			frappe.call({
				method: "mattress_app.api.sales_order.mark_ready_for_dispatch",
				args: { docname: frm.doc.name },
				callback: () => frm.reload_doc(),
			});
		});
		return;
	}

	// Ready for Dispatch / Partially Delivered -> offer 'Mark All Delivered'.
	if (stage === "Ready for Dispatch" || stage === "Partially Delivered") {
		frm.add_custom_button(__("Mark All Delivered"), () => {
			frappe.call({
				method: "mattress_app.api.sales_order.mark_all_delivered",
				args: { docname: frm.doc.name, delivered: 1 },
				callback: () => frm.reload_doc(),
			});
		});
		return;
	}
	// Delivered / Payment Pending / Closed -> no stage button.
}

function show_so_stage_indicator(frm) {
	const stage_colors = {
		"In Production": "orange",
		"Ready for Dispatch": "blue",
		"Partially Delivered": "yellow",
		Delivered: "green",
		Draft: "red",
		Cancelled: "red",
		Overdue: "red",
		Closed: "green",
		"On Hold": "yellow",
		"Due Today": "blue",
		"Payment Pending": "orange",
	};

	// Native lifecycle states ALWAYS win (read straight from native status).
	const native = frm.doc.status;
	if (["On Hold", "Closed", "Cancelled"].includes(native)) {
		frm.page.set_indicator(__(native), stage_colors[native] || "red");
		return;
	}

	// Overdue / Due Today apply only to in-progress (not delivered) stages.
	/*const in_progress = ["In Production", "Ready for Dispatch", "Partially Delivered"].includes(
		custom_status
	);
	const dd = frm.doc.delivery_date;
	if (in_progress && dd) {
		const today = frappe.datetime.get_today();
		if (dd < today) {
			custom_status = "Overdue";
		} else if (dd === today) {
			custom_status = "Due Today";
		}
	}*/

	if (frm.doc.custom_status) {
		frm.page.set_indicator(
			__(frm.doc.custom_status),
			stage_colors[frm.doc.custom_status] || "gray"
		);
	}
	// else: leave native status indicator (fallback / old flow).
}

/* ---------- WhatsApp (DINESH) ---------- */

function strip_html(html) {
	let tmp = document.createElement("DIV");
	tmp.innerHTML = html;
	return tmp.textContent || tmp.innerText || "";
}

function send_whatsapp(frm) {
	let mobile = frm.doc.custom_purchase_mobile;
	if (!mobile) {
		frappe.msgprint(__("Mobile number is missing."));
		return;
	}
	mobile = mobile.replace(/\D/g, "");
	let advance_history_text = "";
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Advance",
			filters: { sale_order_reference: frm.doc.name },
			fields: ["date", "amount", "payment_mode"],
		},
		callback: function (r) {
			if (r.message && r.message.length > 0) {
				advance_history_text = `📝 *ADVANCE HISTORY*\n`;
				r.message.forEach((adv) => {
					advance_history_text += `└ ${frappe.datetime.str_to_user(
						adv.date
					)}: ${format_currency(adv.amount, frm.doc.currency)} (${adv.payment_mode})\n`;
				});
				advance_history_text += `\n`;
			}
			execute_whatsapp_redirect(frm, mobile, advance_history_text);
		},
	});
}

function execute_whatsapp_redirect(frm, mobile, advance_history_text) {
	let advance = frm.doc.advance_paid || 0;
	let rounded_total = frm.doc.rounded_total || frm.doc.grand_total || 0;
	let balance_due = rounded_total - advance;
	let total = rounded_total + frm.doc.discount_amount || 0;

	let items_text = "";
	let items_price = "";
	const hasRealContent = (html) => {
		if (!html) return false;
		return html.replace(/<[^>]*>/g, "").trim().length > 0;
	};

	frm.doc.items.forEach((item, index) => {
		const size =
			item.custom_width && item.custom_length
				? `${item.custom_length}x${item.custom_width}`
				: item.custom_width || "N/A";
		const thickness = item.custom_thickness ? `${item.custom_thickness}` : "";

		const delivered_tag = item.custom_delivered ? " *(Delivered)*" : "";
		items_text += `📦 *${index + 1}. ${item.item_name}*${delivered_tag}\n`;
		items_text += `└ Size: ${size} | Thk: ${thickness} | Qty: ${item.qty}\n`;
		if (item.description && hasRealContent(item.description)) {
			let clean_description = strip_html(item.description).trim();
			if (clean_description) {
				items_text += `└ Specification: ${clean_description}\n\n`;
			} else {
				items_text += `\n`;
			}
		} else {
			items_text += `\n`;
		}
		items_price += `${index + 1}. Price: ${item.rate} | Price: ${item.amount}\n`;
	});

	let message = `*${frm.doc.custom_quotation_reference}*\n`;
	message += `-------------------------------\n\n`;
	message += `${items_text}`;
	message += `👤 *CUSTOMER DETAILS*\n`;
	message += `*Name:* ${frm.doc.customer_name}\n`;
	message += `*Contact:* ${frm.doc.contact_mobile || "N/A"}\n`;
	message += `*Address:* ${
		frm.doc.address_display ? frm.doc.address_display.replace(/<br>/g, ", ") : "N/A"
	}\n\n`;
	message += `💰 *PAYMENT SUMMARY*\n`;
	message += `────────────────\n`;
	message += `*Total Amount:* ${format_currency(total, frm.doc.currency)}\n`;
	if (frm.doc.discount_amount) {
		message += `*Additional Concession:* ${format_currency(
			frm.doc.discount_amount,
			frm.doc.currency
		)}\n`;
	}
	if (frm.doc.rounding_adjustment) {
		message += `*Round Off:* ${format_currency(
			frm.doc.rounding_adjustment,
			frm.doc.currency
		)}\n`;
	}
	message += `*Revised Price:* ${format_currency(rounded_total, frm.doc.currency)}\n`;
	message += `*Advance:* ${format_currency(frm.doc.advance_paid, frm.doc.currency)}\n`;
	message += `*Balance Due:* ${format_currency(balance_due, frm.doc.currency)}\n\n`;
	message += `*Delivery Date:* ${
		frm.doc.delivery_date ? frappe.datetime.str_to_user(frm.doc.delivery_date) : "N/A"
	}\n\n`;
	message += `${items_price}`;
	message += `${advance_history_text}`;

	let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}
