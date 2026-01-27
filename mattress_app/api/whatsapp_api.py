import frappe
from frappe import _
from frappe import _dict
from frappe.utils import flt
from erpnext.stock.get_item_details import get_price_list_rate
import hashlib
import os
from frappe.utils.pdf import get_pdf

###############WHATSAPP API#####################
def generate_public_key(doc, method=None):
    """
    Generates a 16-character secret key if it doesn't exist.
    Hook this to Quotation, Sales Order, and Purchase Order.
    """
    if not doc.get("custom_public_key"):
        doc.custom_public_key = hashlib.sha256(
            os.urandom(16)
        ).hexdigest()[:16]

@frappe.whitelist(allow_guest=True)
def get_public_print_link(doctype, name, key):
    # 1. Allowed Doctypes for Security
    allowed_doctypes = ["Quotation", "Sales Order", "Purchase Order"]
    if doctype not in allowed_doctypes:
        frappe.throw(_("Invalid document type"), frappe.PermissionError)

    # 2. Fetch the secret key from the database
    # Ensure 'custom_public_key' exists in all three Doctypes
    db_key = frappe.db.get_value(doctype, name, "custom_public_key")

    if not db_key or key != db_key:
        frappe.throw(_("Invalid or expired link"), frappe.PermissionError)

    doc = frappe.get_doc(doctype, name)

    # 🔑 Fetch customer type from Customer master
    customer_type = frappe.db.get_value("Customer",doc.customer,"customer_type")

    if customer_type == "Individual":
        print_format = "Sales Order1"
    elif customer_type == "Company":
        print_format = "Sales Order2"

    # 3. Elevate session AND bypass the permission engine
    frappe.set_user("Administrator")
    frappe.flags.ignore_permissions = True 
    
    try:
        # Generate the PDF content
        pdf_content = frappe.get_print(doctype, name, print_format=print_format, as_pdf=True)

        frappe.local.response.filename = f"{name}.pdf"
        frappe.local.response.filecontent = pdf_content
        frappe.local.response.type = "pdf"

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Public PDF Link Error")
        frappe.throw(_("Could not generate PDF. Please contact support."))
        
    finally:
        # 4. Cleanup: Revert user and restore permission checks
        frappe.set_user("Guest")
        frappe.flags.ignore_permissions = False