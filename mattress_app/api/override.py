import json

import frappe
from erpnext.controllers.item_variant import (
	copy_attributes_to_variant,
	generate_keyed_value_combinations,
	get_variant,
)
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from frappe import _
from frappe.utils import cstr, flt


@frappe.whitelist()
def custom_create_variant(item, args, use_template_image=False):
	# ... (existing logic for parsing json and loading template)
	use_template_image = frappe.parse_json(use_template_image)
	if isinstance(args, str):
		args = json.loads(args)

	template = frappe.get_doc("Item", item)
	variant = frappe.new_doc("Item")

	# --- ADD THIS LINE ---
	variant.item_name = template.item_name
	# ---------------------

	variant.variant_based_on = "Item Attribute"
	variant_attributes = []

	for d in template.attributes:
		variant_attributes.append({"attribute": d.attribute, "attribute_value": args.get(d.attribute)})

	variant.set("attributes", variant_attributes)
	copy_attributes_to_variant(template, variant)

	# Re-apply item_name after copy_attributes_to_variant just in case
	# it was overwritten by logic inside that controller function
	variant.item_name = template.item_name

	if use_template_image and template.image:
		variant.image = template.image

	make_variant_item_code(template.item_code, variant)

	return variant


def make_variant_item_code(template_item_code, variant):
	"""Only generate variant item_code"""
	if variant.item_code:
		return

	code_abbreviations = []

	for attr in variant.attributes:
		item_attribute = frappe.db.sql(
			"""select i.numeric_values, v.abbr
               from `tabItem Attribute` i
               left join `tabItem Attribute Value` v
                 on i.name = v.parent
               where i.name=%(attribute)s
                 and (v.attribute_value=%(attribute_value)s or i.numeric_values = 1)""",
			{"attribute": attr.attribute, "attribute_value": attr.attribute_value},
			as_dict=True,
		)

		if not item_attribute:
			continue

		abbr_or_value = (
			cstr(attr.attribute_value) if item_attribute[0].numeric_values else item_attribute[0].abbr
		)

		code_abbreviations.append(abbr_or_value)

	if code_abbreviations:
		variant.item_code = f"{template_item_code}-{'-'.join(code_abbreviations)}"


# create Multiple variant


@frappe.whitelist()
def custom_enqueue_multiple_variant_creation(item, args, use_template_image=False):
	use_template_image = frappe.parse_json(use_template_image)
	if isinstance(args, str):
		variants = json.loads(args)

	total_variants = 1
	for key in variants:
		total_variants *= len(variants[key])

	if total_variants >= 600:
		frappe.throw(_("Please do not create more than 500 items at a time"))
		return

	if total_variants < 10:
		return create_multiple_variants(item, args, use_template_image)
	else:
		# CHANGE THIS LINE: Point to your custom app/module path
		# Format: "your_app.your_module.file_name.create_multiple_variants"
		frappe.enqueue(
			"mattress_app.api.override.create_multiple_variants",
			item=item,
			args=args,
			use_template_image=use_template_image,
			now=frappe.flags.in_test,
		)
		return "queued"


def create_multiple_variants(item, args, use_template_image=False):
	count = 0
	if isinstance(args, str):
		args = json.loads(args)

	template_item = frappe.get_doc("Item", item)
	args_set = generate_keyed_value_combinations(args)

	for attribute_values in args_set:
		if not get_variant(item, args=attribute_values):
			variant = custom_create_variant(item, attribute_values)
			if use_template_image and template_item.image:
				variant.image = template_item.image
			variant.save()
			count += 1

	return count


################## Quotation Net Rate etc Field Logic After Discount##############
class CustomTaxesAndTotals(calculate_taxes_and_totals):
	def apply_discount_amount(self):
		if self.doc.discount_amount:
			if not self.doc.apply_discount_on:
				frappe.throw(_("Please select Apply Discount On"))

			self.doc.base_discount_amount = flt(
				self.doc.discount_amount * self.doc.conversion_rate,
				self.doc.precision("base_discount_amount"),
			)

			if self.doc.apply_discount_on == "Grand Total" and self.doc.get("is_cash_or_non_trade_discount"):
				self.discount_amount_applied = True
				return

			total_for_discount_amount = self.get_total_for_discount_amount()
			net_total = 0
			expected_net_total = 0

			if total_for_discount_amount:
				# calculate item amount after Discount Amount
				for item in self._items:
					distributed_amount = (
						flt(self.doc.discount_amount) * item.net_amount / total_for_discount_amount
					)

					adjusted_net_amount = item.net_amount - distributed_amount
					expected_net_total += adjusted_net_amount

					item.net_amount = flt(
						adjusted_net_amount,
						item.precision("net_amount"),
					)

					item.distributed_discount_amount = flt(
						distributed_amount,
						item.precision("distributed_discount_amount"),
					)

					net_total += item.net_amount

					# discount amount rounding adjustment
					rounding_difference = flt(
						expected_net_total - net_total,
						self.doc.precision("net_total"),
					)

					if rounding_difference:
						item.net_amount = flt(
							item.net_amount + rounding_difference,
							item.precision("net_amount"),
						)

						item.distributed_discount_amount = flt(
							distributed_amount + rounding_difference,
							item.precision("distributed_discount_amount"),
						)

						net_total += rounding_difference

					item.net_rate = (
						flt(
							item.net_amount / item.qty,
							item.precision("net_rate"),
						)
						if item.qty
						else 0
					)

					self._set_in_company_currency(
						item,
						["net_rate", "net_amount"],
					)

				self.discount_amount_applied = True
				self._calculate()
		else:
			self.doc.base_discount_amount = 0
