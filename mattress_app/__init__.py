__version__ = "0.0.1"
import erpnext.controllers.taxes_and_totals as tt

from mattress_app.api.override import CustomTaxesAndTotals

tt.calculate_taxes_and_totals = CustomTaxesAndTotals
