/*frappe.ui.form.on("Purchase Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("WhatsApp"), () => {
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

// WHATSAPP QUOTATION SENDING LOGIC
function send_whatsapp(frm) {
	// 1. Force a refresh if the key is missing but the doc is saved
	if (!frm.doc.custom_public_key && !frm.is_dirty()) {
		frm.reload_doc();
	}

	let mobile = frm.doc.contact_mobile || frm.doc.mobile_no;

	if (!mobile) {
		frappe.msgprint(__("Mobile number is missing."));
		return;
	}

	frappe.db.get_value("Purchase Order", frm.doc.name, "custom_public_key").then((r) => {
		const key = r.message?.custom_public_key;

		if (!key) {
			frappe.msgprint(
				__("Access key not generated. Please Save the document to generate one.")
			);
			return;
		}

		send_whatsapp_with_key(frm, key);
	});

	mobile = mobile.replace(/\D/g, "");
	const base_url = window.location.origin;

	// Using your specific app path
	let pdf_url = `${base_url}/api/method/mattress_app.api.whatsapp_api.get_public_print_link?doctype=Purchase%20Order&name=${frm.doc.name}&key=${frm.doc.custom_public_key}`;

	let message =
		`*Hello ${frm.doc.supplier},*\n\n` +
		`Please find your Purchase Order *${frm.doc.name}* attached below.\n\n` +
		`*Total:* ${format_currency(frm.doc.grand_total, frm.doc.currency)}\n\n` +
		`*Download Link:*\n${pdf_url}\n\n` +
		`Regards,\n${frm.doc.company}`;

	let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
	window.open(url, "_blank");
}
*/
