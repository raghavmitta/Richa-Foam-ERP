/* global mattress_app */
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (!frm.is_new()) mattress_app.utils.render_advance_tracker(frm);
		if (!frm.is_new() && frm.doc.docstatus !== 2) {
			frm.add_custom_button(__("Record Advance"), function () {
				mattress_app.utils.add_advance_payment(frm);
			}).addClass("btn-primary"); // Makes the button blue and easy to see on a tablet
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
			frm.add_custom_button(__("WA DINESH"), () => {
				send_whatsapp(frm);
			})
				.addClass("btn-success")
				.css({
					border: "1px solid #25D366",
					color: "#25D366", // Official WhatsApp Green
					"background-color": "white",
				});
		}
	},
});
function strip_html(html) {
	let tmp = document.createElement("DIV");
	tmp.innerHTML = html;
	return tmp.textContent || tmp.innerText || "";
}

// WHATSAPP SALES ORDER SENDING LOGIC FOR DINESH BHAI
function send_whatsapp(frm) {
	// 1. Force a refresh if the key is missing but the doc is saved

	let mobile = frm.doc.custom_purchase_mobile;

	if (!mobile) {
		frappe.msgprint(__("Mobile number is missing."));
		return;
	}

	mobile = mobile.replace(/\D/g, "");
	const base_url = window.location.origin;
	let advance_history_text = "";
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Advance",
			filters: { sale_order_reference: frm.doc.name },
			fields: ["date", "amount", "payment_mode"],
		},
		callback: function (r) {
			let total_advance = 0;

			if (r.message && r.message.length > 0) {
				advance_history_text = `📝 *ADVANCE HISTORY*\n`;
				r.message.forEach((adv, i) => {
					total_advance += flt(adv.amount);
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
	// Calculate the Balance Due manually

	let advance = frm.doc.advance_paid || 0;
	let rounded_total = frm.doc.rounded_total || frm.doc.grand_total || 0;
	let balance_due = rounded_total - advance;
	let total = rounded_total + frm.doc.discount_amount || 0;

	/// Map the items into a clean, scannable list
	let items_text = "";
	let items_price = "";
	const hasRealContent = (html) => {
		if (!html) return false;
		// Removes HTML tags and checks if anything besides whitespace remains
		return html.replace(/<[^>]*>/g, "").trim().length > 0;
	};

	frm.doc.items.forEach((item, index) => {
		// Formatting dimensions for better readability
		const size =
			item.custom_width && item.custom_length
				? `${item.custom_length}x${item.custom_width}`
				: item.custom_width || "N/A";
		const thickness = item.custom_thickness ? `${item.custom_thickness}` : "";

		items_text += `📦 *${index + 1}. ${item.item_name}*\n`;
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

	// Construct the message with clear sections
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

	// Use the message variable in your WhatsApp trigger
	let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}
