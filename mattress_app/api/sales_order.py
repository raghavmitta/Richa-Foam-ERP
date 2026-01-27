import frappe

def add_purchase_mobile(doc, method):
    add_sales_person(doc)
    if doc.company:
        doc.custom_quotation_reference = doc.items[0].prevdoc_docname
        purchase_mobile = frappe.db.get_value("Company", doc.company, "custom_purchase_mobile_no")
        if purchase_mobile:
            doc.custom_purchase_mobile = purchase_mobile

def add_sales_person(doc):
    sales_person = frappe.get_value("Quotation", doc.custom_quotation_reference, "custom_salesman")
    if sales_person:
        doc.append("sales_team", {
            "sales_person": sales_person,
            "allocated_percentage": 100
        })   