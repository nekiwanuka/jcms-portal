from django.urls import path

from . import views

urlpatterns = [
	path("", views.documents_archive, name="documents_archive"),
	path("upload/", views.upload_document, name="upload_document"),
	path("<int:doc_id>/download/", views.download_document, name="download_document"),
	path("<int:doc_id>/send/", views.send_document, name="send_document"),
]
