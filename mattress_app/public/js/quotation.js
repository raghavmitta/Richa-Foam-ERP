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
    discount_percentage: (frm) => frm.events.delayed_calculate(frm)

});

frappe.ui.form.on('Quotation', {
    // refresh(frm) {
    //     if (frm.doc.docstatus === 1) {
    //         frm.add_custom_button(__("WhatsApp"), () => {
    //             send_quotation_whatsapp(frm);
    //         })
    //             .addClass('btn-success')
    //             .css({
    //                 'border': '1px solid #25D366',
    //                 'color': '#25D366', // Official WhatsApp Green
    //                 'background-color': 'white'
    //             });
    //     }
    // },
    // Parent level triggers
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

        (frm.doc.items || []).forEach(item => {
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
        frm.set_value('custom_non_discount_total', non_discount_total);
        frm.set_value('custom_discount_items_total', discountable_total);
        frm.set_value('custom_other_items_mrp_total', custom_other_items_mrp_total);
        frm.set_value('custom_mattress_items_mrp_total', custom_mattress_items_mrp_total);

        frm.refresh_field('custom_non_discount_total');
        frm.refresh_field('custom_discount_items_total');
        frm.refresh_field('custom_other_items_mrp_total');
        frm.refresh_field('custom_mattress_items_mrp_total');
    }
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
        frappe.db.get_list("Item", {
            filters: { "item_name": row.custom_name },
            fields: ["variant_of"],
            limit: 1
        }).then(res => {
            // If the first item found has a 'variant_of', treat the whole group as variants
            const template_item = (res.length > 0) ? res[0].variant_of : null;
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
                custom_name: row.custom_name
            },
            callback(r) {
                if (r.message && r.message.variant_item) {
                    // ✅ SUCCESS: Variant found
                    frappe.model.set_value(cdt, cdn, {
                        item_code: r.message.variant_item,
                        custom_standard_width: r.message.selected_width,
                        custom_standard_length: r.message.selected_length
                    });

                    // Sync discount status and calculate totals
                    sync_non_discount_status(frm, cdt, cdn);
                } else {
                    // ❌ NOT FOUND: Reset item-specific fields but KEEP dimensions
                    frappe.model.set_value(cdt, cdn, {
                        custom_name: null,
                        custom_thickness: null,
                        custom_width: null,
                        custom_length: null
                    });

                    // Inform the user so they know to change dimensions
                    frappe.msgprint({
                        message: ("⚠️ No variant for these standard dimensions."),
                        indicator: 'red'
                    });
                }

                VARIANT_LOCK[cdn] = false;
            }
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

    frappe.db.get_list("Item", {
        filters: { "item_name": row.custom_name },
        fields: ["name", "custom_discount_applicable"], // In ERPNext, the 'name' field IS the item_code
        limit: 1
    }).then(res => {
        if (res && res.length > 0) {
            // 2. Set the Item Code and clear any old standard dimensions
            frappe.model.set_value(cdt, cdn, {
                "item_code": res[0].name,
            });
        }
    }).finally(() => {
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
            frappe.model.set_value(cdt, cdn, 'custom_item_price_rate', item.price_list_rate);
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

            // 2. Toggle the UI
            toggle_discount_fields(frm, cdt, cdn, is_non_discount);

            // 3. NOW trigger the calculation (Data is ready!)
            frm.events.delayed_calculate(frm);
        }
    });
}

// WHATSAPP QUOTATION SENDING LOGIC
function send_quotation_whatsapp(frm) {
    // 1. Force a refresh if the key is missing but the doc is saved
    if (!frm.doc.public_print_key && !frm.is_dirty()) {
        frm.reload_doc();
    }

    let mobile = frm.doc.contact_mobile || frm.doc.mobile_no;

    if (!mobile) {
        frappe.msgprint(__("Customer mobile number is missing."));
        return;
    }

    frappe.db.get_value(
        "Quotation",
        frm.doc.name,
        "custom_public_key"
    ).then(r => {
        const key = r.message?.custom_public_key;

        if (!key) {
            frappe.msgprint(__("Access key not generated. Please Save the document to generate one."));
            return;
        }

        send_whatsapp_with_key(frm, key);
    });


    mobile = mobile.replace(/\D/g, "");
    const base_url = window.location.origin;

    // Using your specific app path
    let pdf_url = `${base_url}/api/method/mattress_app.api.whatsapp_api.get_public_print_link?doctype=Quotation&name=${frm.doc.name}&key=${frm.doc.custom_public_key}`;

    let message = `*Hello ${frm.doc.customer_name},*\n\n` +
        `Please find your quotation *${frm.doc.name}* attached below.\n\n` +
        `*Total:* ${format_currency(frm.doc.grand_total, frm.doc.currency)}\n\n` +
        `*Download Link:*\n${pdf_url}\n\n` +
        `Regards,\n${frm.doc.company}`;

    let url = `https://wa.me/${mobile}?text=${encodeURIComponent(message)}`;
    window.open(url, "_blank");
}



