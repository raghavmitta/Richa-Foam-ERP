import mattress_app

app_name = "mattress_app"
app_title = "Mattress"
app_publisher = "Hitc Technologies"
app_description = "Matress App"
app_email = "hitctechnologies@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "mattress_app",
# 		"logo": "/assets/mattress_app/logo.png",
# 		"title": "Mattress",
# 		"route": "/mattress_app",
# 		"has_permission": "mattress_app.api.permission.has_app_permission"
# 	}
# ]
# In hooks.py
app_include_js = "/assets/mattress_app/js/payment_utils.js"
doctype_js = {
	"Quotation": "public/js/quotation.js",
	"Sales Order": "public/js/sales_order.js",
	# "Purchase Order": "public/js/purchase_order.js",
	# "Customer": "public/js/customer.js"
}

fixtures = [
	"Custom Field",
	"Property Setter",
	{"dt": "Custom DocPerm", "filters": [["parent", "=", "Quotation"], ["role", "=", "Guest"]]},
	{"dt": "Currency", "filters": [["name", "=", "INR"]]},
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/mattress_app/css/mattress_app.css"
# app_include_js = "/assets/mattress_app/js/customer.js"

# include js, css files in header of web template
# web_include_css = "/assets/mattress_app/css/mattress_app.css"
# web_include_js = "/assets/mattress_app/js/mattress_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "mattress_app/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "mattress_app/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "mattress_app.utils.jinja_methods",
# 	"filters": "mattress_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "mattress_app.install.before_install"
# after_install = "mattress_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "mattress_app.uninstall.before_uninstall"
# after_uninstall = "mattress_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "mattress_app.utils.before_app_install"
# after_app_install = "mattress_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "mattress_app.utils.before_app_uninstall"
# after_app_uninstall = "mattress_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "mattress_app.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"Quotation":"mattress_app.api.override.CustomQuotation",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Item": {
		"validate": "mattress_app.api.item.create_item_name_doc",
		"on_trash": "mattress_app.api.item.cleanup_item_name_doc",
		"before_save": "mattress_app.api.item.remove_description",
	},
	"Item Attribute": {
		"validate": "mattress_app.api.item_variant.sync_thickness_from_item_attribute",
		"before_update": "mattress_app.api.item_variant.sync_thickness_delete",
	},
	"Quotation": {
		"validate": "mattress_app.api.quotation.rate_lower_warning",
		"before_save": [
			"mattress_app.api.quotation.additional_discount",
			"mattress_app.api.whatsapp_api.generate_public_key",
		],
		"before_submit": "mattress_app.api.quotation.address_mandatory_check",
		"after_insert": ["mattress_app.api.advance_linker.handleQuotationAmendmends"],
	},
	"Advance": {
		"before_insert": "mattress_app.api.advance_linker.validateAndLinkReferences",
		"after_insert": "mattress_app.api.advance_linker.processNewAdvance",
	},
	"Sales Order": {
		"on_cancel": "mattress_app.api.advance_linker.handleSoCancellation",
		"after_insert": "mattress_app.api.advance_linker.UpdateAdvanceWithSalesOrderReference",
		"before_save": "mattress_app.api.sales_order.add_purchase_mobile",
		"on_submit": "mattress_app.api.advance_linker.createOrUpdatePendingPaymentEntry",
	},
}


# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"mattress_app.tasks.all"
# 	],
# 	"daily": [
# 		"mattress_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"mattress_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"mattress_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"mattress_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "mattress_app.install.before_tests"

# Overriding Methods
# ------------------------------
# # erpnext item variant file and method name = custom app file and method name
override_whitelisted_methods = {
	"erpnext.controllers.item_variant.create_variant": "mattress_app.api.override.custom_create_variant",
	"erpnext.controllers.item_variant.enqueue_multiple_variant_creation": "mattress_app.api.override.custom_enqueue_multiple_variant_creation",
}

#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "mattress_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["mattress_app.utils.before_request"]
# after_request = ["mattress_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["mattress_app.utils.before_job"]
# after_job = ["mattress_app.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"mattress_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
