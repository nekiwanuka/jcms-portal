from rest_framework.routers import DefaultRouter

from appointments.api import AppointmentViewSet
from clients.api import ClientViewSet
from core.api import BranchViewSet
from documents.api import DocumentViewSet
from inventory.api import ProductCategoryViewSet, ProductViewSet, StockMovementViewSet, SupplierViewSet
from invoices.api import InvoiceItemViewSet, InvoiceViewSet, PaymentViewSet
from sales.api import QuotationItemViewSet, QuotationViewSet

router = DefaultRouter()

router.register(r"branches", BranchViewSet, basename="branch")
router.register(r"clients", ClientViewSet, basename="client")

router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"product-categories", ProductCategoryViewSet, basename="productcategory")
router.register(r"products", ProductViewSet, basename="product")
router.register(r"stock-movements", StockMovementViewSet, basename="stockmovement")

router.register(r"quotations", QuotationViewSet, basename="quotation")
router.register(r"quotation-items", QuotationItemViewSet, basename="quotationitem")

router.register(r"invoices", InvoiceViewSet, basename="invoice")
router.register(r"invoice-items", InvoiceItemViewSet, basename="invoiceitem")
router.register(r"payments", PaymentViewSet, basename="payment")

router.register(r"appointments", AppointmentViewSet, basename="appointment")
router.register(r"documents", DocumentViewSet, basename="document")

urlpatterns = router.urls
