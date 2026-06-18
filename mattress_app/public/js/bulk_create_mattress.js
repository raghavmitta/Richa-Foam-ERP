/* Module 4 : "Create Mattress Model" dialog.
 *
 * Adds a button on the Item list view that opens a dialog to bulk-create a new
 * mattress model across several thicknesses with brand-first naming + area
 * pricing. Wire via hooks.py:
 *     doctype_list_js = {"Item": "public/js/bulk_create_mattress.js"}
 */

frappe.listview_settings = frappe.listview_settings || {};
frappe.listview_settings["Item"] = frappe.listview_settings["Item"] || {};

const _orig_item_onload = frappe.listview_settings["Item"].onload;

frappe.listview_settings["Item"].onload = function (listview) {
	if (_orig_item_onload) {
		try {
			_orig_item_onload(listview);
		} catch (e) {
			// don't let an existing handler block our button
			console.error(e);
		}
	}

	listview.page.add_inner_button(__("Create Mattress Model"), function () {
		open_create_model_dialog();
	});
};

function open_create_model_dialog() {
	const d = new frappe.ui.Dialog({
		title: __("Create Mattress Model"),
		size: "large",
		fields: [
			{
				fieldname: "brand",
				fieldtype: "Link",
				label: __("Brand"),
				options: "Brand",
				reqd: 1,
				description: __(
					"Pick an existing brand, or type a new name and choose 'Create a new Brand'."
				),
			},
			{
				fieldname: "model",
				fieldtype: "Data",
				label: __("Model Name"),
				description: __("e.g. Naturalite. Item code becomes 'Brand Model-<thk>MM'."),
				reqd: 1,
			},
			{
				fieldname: "item_group",
				fieldtype: "Link",
				label: __("Item Group"),
				options: "Item Group",
				default: "Products",
			},
			{
				fieldname: "stock_uom",
				fieldtype: "Link",
				label: __("UOM"),
				options: "UOM",
				default: "Nos",
			},
			{
				fieldname: "gst_hsn_code",
				fieldtype: "Data",
				label: __("HSN Code (optional)"),
			},
			{ fieldtype: "Section Break", label: __("Thicknesses & 72×72 Prices") },
			{
				fieldname: "rows",
				fieldtype: "Table",
				label: __("Thickness Rows"),
				cannot_add_rows: false,
				in_place_edit: true,
				reqd: 1,
				data: [],
				fields: [
					{
						fieldname: "thickness",
						fieldtype: "Int",
						label: __("Thickness (mm)"),
						in_list_view: 1,
						reqd: 1,
					},
					{
						fieldname: "price_72",
						fieldtype: "Currency",
						label: __("72×72 Price"),
						in_list_view: 1,
						reqd: 1,
					},
				],
			},
			{ fieldtype: "HTML", fieldname: "preview" },
		],
		primary_action_label: __("Create Items"),
		primary_action(values) {
			const rows = (values.rows || []).filter((r) => r.thickness && r.price_72);
			if (!rows.length) {
				frappe.msgprint(__("Add at least one thickness row with a price."));
				return;
			}

			frappe.call({
				method: "mattress_app.api.bulk_create_mattress.create_model",
				args: {
					brand: values.brand,
					model: values.model,
					rows: JSON.stringify(rows),
					item_group: values.item_group,
					stock_uom: values.stock_uom,
					gst_hsn_code: values.gst_hsn_code,
				},
				freeze: true,
				freeze_message: __("Creating items…"),
				callback(r) {
					if (r.message) {
						const m = r.message;
						let html = `<b>${frappe.utils.escape_html(m.family)}</b><br>`;
						if (m.created && m.created.length) {
							html +=
								__("Created:") +
								"<br>" +
								m.created
									.map((c) => "• " + frappe.utils.escape_html(c))
									.join("<br>");
						}
						if (m.skipped && m.skipped.length) {
							html +=
								"<br><br>" +
								__("Already existed (price updated):") +
								"<br>" +
								m.skipped
									.map((c) => "• " + frappe.utils.escape_html(c))
									.join("<br>");
						}
						frappe.msgprint({ title: __("Done"), message: html, indicator: "green" });
						d.hide();
						cur_list && cur_list.refresh && cur_list.refresh();
					}
				},
			});
		},
	});

	// live preview of resulting item codes
	const update_preview = () => {
		const brand = d.get_value("brand");
		const model = d.get_value("model");
		const rows = d.get_value("rows") || [];
		if (!brand || !model) {
			d.fields_dict.preview.$wrapper.html("");
			return;
		}
		const family = `${brand} ${model}`.trim();
		const lines = rows
			.filter((r) => r.thickness)
			.map(
				(r) =>
					`• <code>${frappe.utils.escape_html(family)}-${r.thickness}MM</code>` +
					(r.price_72 ? ` &nbsp;→ rate/sqin ≈ ${(r.price_72 / 5184).toFixed(4)}` : "")
			);
		d.fields_dict.preview.$wrapper.html(
			`<div class="text-muted" style="margin-top:8px;">` +
				__("Will create:") +
				`<br>${lines.join("<br>") || "—"}</div>`
		);
	};

	d.fields_dict.brand.df.onchange = update_preview;
	d.fields_dict.model.df.onchange = update_preview;
	d.fields_dict.rows.grid.wrapper.on("change", update_preview);

	d.show();
}
