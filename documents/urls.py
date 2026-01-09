from django.urls import path

from . import views

urlpatterns = [
	path("", views.documents_archive, name="documents_archive"),
	path("upload/", views.upload_document, name="upload_document"),
	path("<int:doc_id>/download/", views.download_document, name="download_document"),
	path("<int:doc_id>/send/", views.send_document, name="send_document"),
	path("<int:doc_id>/approve/", views.approve_document, name="approve_document"),
	path("<int:doc_id>/reject/", views.reject_document, name="reject_document"),
	path("<int:doc_id>/sign/", views.sign_document, name="sign_document"),
	path("<int:doc_id>/remove-signature/", views.remove_signature, name="remove_signature"),
	path("<int:doc_id>/verification-status/", views.document_verification_status, name="document_verification_status"),
]
