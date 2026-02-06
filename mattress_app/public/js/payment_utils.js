/* global mattress_app */
frappe.provide("mattress_app.utils");

mattress_app.utils.add_advance_payment = function (frm) {
	let total_rounded = flt(frm.doc.rounded_total) || flt(frm.doc.grand_total);
	let previous_advance = flt(frm.doc.advance_paid) || 0;

	let d = new frappe.ui.Dialog({
		title: __("Record Advance (Pending Entry)"),
		fields: [
			{
				label: "Summary",
				fieldname: "summary_html",
				fieldtype: "HTML",
				options: `
                    <div style="background: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #d1d8dd;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                            <span>Total Rounded Amount:</span> <strong>${format_currency(
								total_rounded,
								frm.doc.currency
							)}</strong>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span>Advance Till Now:</span> <strong>${format_currency(
								previous_advance,
								frm.doc.currency
							)}</strong>
                        </div>
                    </div>`,
			},
			{ fieldtype: "Section Break" },
			{
				label: "Current Amount",
				fieldname: "amount",
				fieldtype: "Currency",
				reqd: 1,
				onchange: () => update_balance(),
			},
			{ fieldtype: "Column Break" },
			{
				label: "Mode of Payment",
				fieldname: "mode_of_payment",
				fieldtype: "Link",
				options: "Mode of Payment",
				reqd: 1,
			},
			{ fieldtype: "Section Break" },
			{
				label: "Balance Due",
				fieldname: "balance_due_html",
				fieldtype: "HTML",
				options: `
                    <div id="balance_container" style="font-size: 1.1em; font-weight: bold; text-align: center; padding: 10px; border-radius: 5px; background: #fff3cd;">
                        Balance Due: <span id="balance_val">${format_currency(
							total_rounded - previous_advance,
							frm.doc.currency
						)}</span>
                    </div>`,
			},
		],
		primary_action_label: __("Log Advance"),
		primary_action(values) {
			let current_amt = flt(values.amount);
			let balance = total_rounded - previous_advance - current_amt;

			// 2. Strict Negative Check
			if (balance < -0.01) {
				// Allowing small float margin
				frappe.msgprint({
					title: __("Invalid Amount"),
					indicator: "red",
					message: __("Advance cannot exceed the total balance due of {0}", [
						format_currency(total_rounded - previous_advance, frm.doc.currency),
					]),
				});
				return;
			}

			d.hide();
			create_payment_entry(values);
		},
	});

	function update_balance() {
		let current = flt(d.get_value("amount"));
		let remaining = total_rounded - previous_advance - current;
		let color = remaining < 0 ? "#f8d7da" : remaining <= 9 ? "#d4edda" : "#fff3cd";
		let text_color = remaining < 0 ? "#721c24" : "#856404";

		$("#balance_val").text(format_currency(remaining, frm.doc.currency));
		$("#balance_container").css({ "background-color": color, color: text_color });
	}
	function create_payment_entry(values) {
		frappe.call({
			method: "frappe.client.insert",
			async: false,
			args: {
				doc: {
					doctype: "Advance",
					quotation_reference: frm.doctype === "Quotation" ? frm.doc.name : null,
					sale_order_reference: frm.doctype === "Sales Order" ? frm.doc.name : null,
					amount: values.amount,
					payment_mode: values.mode_of_payment, // Your external Ref (GPay/Cheque) // <--- THIS STAYS EMPTY FOR NOW
					date: frappe.datetime.nowdate(),
				},
			},
			callback: function (r) {
				if (!r.exc) {
					mattress_app.utils.render_advance_tracker(frm);
					frappe.show_alert({ message: __("Advance Recorded"), indicator: "green" });
					// Update UI Child Table for visual tracking
					frm.reload_doc();
				}
			},
		});
	}
	d.show();
};

// Universal function to render the tracker table
mattress_app.utils.render_advance_tracker = function (frm) {
	// 1. Define the filters dynamically based on the current DocType
	let filters = {};
	if (frm.doctype === "Quotation") {
		filters = { quotation_reference: frm.doc.name };
	} else if (frm.doctype === "Sales Order") {
		filters = { sale_order_reference: frm.doc.name };
	}

	// 2. Fetch data from the Advance Tracker DocType
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Advance",
			filters: filters,
			order_by: "creation desc",
			fields: [
				"name",
				"date",
				"amount",
				"payment_mode",
				"payment_reference_number",
				"sale_order_reference",
				"quotation_reference",
			],
		},
		async: true,
		callback: function (r) {
			let total_advance = 0;
			let html = `
                <div class="advance-tracker-container">
                    <table class="table table-bordered table-condensed" style="background-color: #f9f9f9; font-size: 13px;">
                        <thead style="background-color: #ebebeb;">
                            <tr>
                                <th style="width: 20%">${__("Date")}</th>
                                <th style="width: 25%">${__("Amount")}</th>
                                <th style="width: 20%">${__("Mode")}</th>
                                <th style="width: 20%">${__("Status")}</th>
                            </tr>
                        </thead>
                        <tbody>`;

			if (!r.message || r.message.length === 0) {
				html += `<tr><td colspan="5" class="text-center text-muted">${__(
					"No advance payments recorded."
				)}</td></tr>`;
			} else {
				r.message.forEach((row) => {
					let status_badge = `<span class="badge badge-danger">Pending SO Creation</span>`;
					status_badge = row.sale_order_reference
						? `<span class="badge badge-warning">Pending SO Submission:${row.sale_order_reference}</span>`
						: `<span class="badge badge-danger">Pending SO Creation</span>`;
					if (row.sale_order_reference)
						status_badge = row.payment_reference_number
							? `<span class="badge badge-success">Linked: ${row.payment_reference_number}</span>`
							: `<span class="badge badge-warning">Pending SO Submission:${row.sale_order_reference}</span>`;
					total_advance += row.amount;
					html += `
                        <tr>
                            <td>${frappe.datetime.str_to_user(row.date)}</td>
                            <td style="font-weight: bold; color: #2ecc71;">${format_currency(
								row.amount,
								frm.doc.currency
							)}</td>
                            <td>${row.payment_mode}</td>
                            <td>${status_badge}</td>
                        </tr>`;
				});
			}

			html += `</tbody></table></div>`;

			// 3. Inject the HTML into the field
			if (frm.get_field("custom_advance_payment_tracker")) {
				frm.get_field("custom_advance_payment_tracker").$wrapper.html(html);
			}
			// Check if the database needs an update
			if (frm.doc.advance_paid !== total_advance) {
				frappe.call({
					method: "mattress_app.api.advance_linker.updateAdvancePaidSilently",
					args: {
						doctype: frm.doctype,
						name: frm.doc.name,
						total_advance: total_advance,
					},
					callback: function (r) {
						if (!r.exc) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Advance Updated Silently"),
								indicator: "blue",
							});
						}
					},
				});
			}
		},
	});
};
