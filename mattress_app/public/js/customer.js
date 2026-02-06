alert("CUSTOMER.JS LOADED");

frappe.provide("frappe.ui.form");
alert("CUSTOMER.JS LOADED");

console.log("🔥 mattress_app customer.js loaded");

function patch_quick_entry() {
	const QE = frappe.ui.form.ContactAddressQuickEntryForm;

	if (!QE) {
		setTimeout(patch_quick_entry, 100);
		return;
	}

	console.log("✅ Patching ContactAddressQuickEntryForm");

	const original = QE.prototype.get_variant_fields;

	QE.prototype.get_variant_fields = function () {
		const fields = original.call(this);
		console.log("🧩 get_variant_fields patched");

		fields.forEach((df) => {
			if (df.fieldname === "mobile_number") {
				df.reqd = 1;
			}
		});

		return fields;
	};
}

frappe.ready(patch_quick_entry);
