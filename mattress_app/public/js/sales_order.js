frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
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
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("WhatsApp"), () => {
				generate_whatsapp_link(frm);
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

// WHATSAPP SALES ORDER SENDING LOGIC FOR DINESH BHAI
function send_whatsapp(frm) {
	// 1. Force a refresh if the key is missing but the doc is saved
	if (!frm.is_dirty()) {
		frm.reload_doc();
	}

	let mobile = frm.doc.custom_purchase_mobile;

	if (!mobile) {
		frappe.msgprint(__("Mobile number is missing."));
		return;
	}

	mobile = mobile.replace(/\D/g, "");
	const base_url = window.location.origin;

	// Calculate the Balance Due manually
	let grand_total = frm.doc.grand_total || 0;
	let advance = frm.doc.advance_paid || 0;
	let balance_due = grand_total - advance;
	let total = grand_total + frm.doc.discount_amount || 0;

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
			items_text += `└ Description: ${item.description}\n\n`;
		} else {
			items_text += `\n`;
		}
		items_price += `${index + 1}. Custom Price: ${item.rate} | Price: ${item.amount}\n`;
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
	message += `*Total Amount:* ${format_currency(frm.doc.total, frm.doc.currency)}\n`;
	message += `*Revised Price:* ${format_currency(frm.doc.grand_total, frm.doc.currency)}\n`;
	if (frm.doc.rounding_adjustment) {
		message += `*Round Off:* ${format_currency(
			frm.doc.rounding_adjustment,
			frm.doc.currency
		)}\n`;
	}
	message += `*Advance:* ${format_currency(frm.doc.advance_paid, frm.doc.currency)}\n`;
	message += `*Balance Due:* ${format_currency(balance_due, frm.doc.currency)}\n\n`;

	message += `*Delivery Date:* ${
		frm.doc.delivery_date ? frappe.datetime.str_to_user(frm.doc.delivery_date) : "N/A"
	}\n\n`;
	message += `${items_price}`;

	// Use the message variable in your WhatsApp trigger
	let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}
// CUSTOMER WHATSAPP SENDING LOGIC ENDS

// WHATSAPP QUOTATION SENDING LOGIC
/*function send_customer_whatsapp(frm) {
	// 1. Force a refresh if the key is missing but the doc is saved
	if (!frm.is_dirty()) {
		frm.reload_doc();
	}

	let mobile = frm.doc.contact_mobile || frm.doc.mobile_no;

	if (!mobile) {
		frappe.msgprint(__("Customer mobile number is missing."));
		return;
	}

	frappe.db.get_value("Sales Order", frm.doc.name, "key").then((r) => {
		const key = r.message?.custom_public_key;

		generate_whatsapp_link(frm)
	});

	mobile = mobile.replace(/\D/g, "");
	const base_url = frappe.base_url || window.location.origin;
	frappe.msgprint("Step 2: URL generated: " + base_url);

	// Using your specific app path
	let pdf_url = `${base_url}/api/method/mattress_app.api.whatsapp_api.get_public_print_link?doctype=Sales%20Order&name=${frm.doc.name}&key=${frm.doc.custom_public_key}`;

	let message =
		`*Hello ${frm.doc.customer_name},*\n\n` +
		`Please find your quotation *${frm.doc.custom_quotation_reference}* attached below.\n\n` +
		`*Total:* ${format_currency(frm.doc.grand_total, frm.doc.currency)}\n\n` +
		`*Download Link:*\n${pdf_url}\n\n` +
		`Regards,\n${frm.doc.company}`;

	let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}*/

function generate_whatsapp_link(frm) {
	// Show a loading state for the tablet/mobile users
	frappe.dom.freeze(__("Generating secure link..."));

	frappe.call({
		method: "mattress_app.api.whatsapp_api.get_public_print_link", // Adjust path to your Python file
		args: {
			doctype: frm.doc.doctype,
			name: frm.doc.name,
		},
		callback: function (r) {
			frappe.dom.unfreeze();

			if (r.message) {
				const pdf_url = r.message;

				// Handle Phone Number (Checking multiple fields just in case)
				const phone = frm.doc.contact_mobile || frm.doc.mobile_no;

				if (!phone) {
					frappe.msgprint(
						__("Please ensure a mobile number is entered in the Contact Mobile field.")
					);
					return;
				}

				const message =
					`*Hello ${frm.doc.customer_name},*\n\n` +
					`Please find your quotation *${frm.doc.custom_quotation_reference}* attached below.\n\n` +
					`*Total:* ${format_currency(frm.doc.grand_total, frm.doc.currency)}\n\n` +
					`*Order Pdf Link:*\n${pdf_url}\n\n` +
					`Regards,\n${frm.doc.company}`;

				// Open WhatsApp in a new tab
				const wa_url = `https://api.whatsapp.com/send?phone=${phone}&text=${encodeURIComponent(
					message
				)}`;
				window.open(wa_url, "_blank");
			}
		},
	});
}
