# import json

# import frappe
# from frappe import _, scrub
# from frappe.model.document import Document
# from frappe.utils import cint, flt, round_based_on_smallest_currency_fraction
# from frappe.utils.deprecations import deprecated

# import erpnext
# from erpnext.accounts.doctype.journal_entry.journal_entry import get_exchange_rate
# from erpnext.accounts.doctype.pricing_rule.utils import get_applied_pricing_rules
# from erpnext.controllers.accounts_controller import (
# 	validate_conversion_rate,
# 	validate_inclusive_tax,
# 	validate_taxes_and_charges,
# )
# from erpnext.stock.get_item_details import _get_item_tax_template, get_item_tax_map
# from erpnext.utilities.regional import temporary_flag
# from erpnext.controllers.taxes_and_totals.py import calculate_taxes_and_totals

# class CustomQuotation(calculate_taxes_and_totals):

#     # def custom_apply_discount_amount(self):
#     #     frappe.msgprint("Function call")
#     #     if self.doc.discount_amount:
#     #         if not self.doc.apply_discount_on:
#     #             frappe.throw(_("Please select Apply Discount On"))

#     #         self.doc.base_discount_amount = flt(
#     #             self.doc.discount_amount * self.doc.conversion_rate,
#     #             self.doc.precision("base_discount_amount"),
#     #         )

#     #         if (
#     #             self.doc.apply_discount_on == "Grand Total"
#     #             and self.doc.get("is_cash_or_non_trade_discount")
#     #         ):
#     #             self.discount_amount_applied = True
#     #             return

#     #         total_for_discount_amount = self.get_total_for_discount_amount()
#     #         net_total = 0
#     #         expected_net_total = 0

#     #         if total_for_discount_amount:
#     #             # calculate item amount after Discount Amount
#     #             for item in self._items:
#     #                 distributed_amount = (
#     #                     flt(self.doc.discount_amount)
#     #                     * item.net_amount
#     #                     / total_for_discount_amount
#     #                 )

#     #                 adjusted_net_amount = item.net_amount - distributed_amount
#     #                 expected_net_total += adjusted_net_amount

#     #                 item.net_amount = flt(
#     #                     adjusted_net_amount, item.precision("net_amount")
#     #                 )

#     #                 item.distributed_discount_amount = flt(
#     #                     distributed_amount,
#     #                     item.precision("distributed_discount_amount"),
#     #                 )

#     #                 net_total += item.net_amount

#     #                 # rounding adjustment
#     #                 rounding_difference = flt(
#     #                     expected_net_total - net_total,
#     #                     self.doc.precision("net_total"),
#     #                 )

#     #                 if rounding_difference:
#     #                     item.net_amount = flt(
#     #                         item.net_amount + rounding_difference,
#     #                         item.precision("net_amount"),
#     #                     )
#     #                     item.distributed_discount_amount = flt(
#     #                         item.distributed_discount_amount + rounding_difference,
#     #                         item.precision("distributed_discount_amount"),
#     #                     )
#     #                     net_total += rounding_difference

#     #                 # 🔒 DO NOT CHANGE RATE / NET RATE FOR QUOTATION
#     #                 if self.doc.doctype != "Quotation":
#     #                     item.net_rate = (
#     #                         flt(
#     #                             item.net_amount / item.qty,
#     #                             item.precision("net_rate"),
#     #                         )
#     #                         if item.qty
#     #                         else 0
#     #                     )
#     #                 else:
#     #                     # keep original rate
#     #                     item.net_rate = item.rate

#     #                 self._set_in_company_currency(
#     #                     item, ["net_rate", "net_amount"]
#     #                 )

#     #             self.discount_amount_applied = True
#     #             self._calculate()

#     #     else:
#     #         self.doc.base_discount_amount = 0
