from django.urls import path

from . import views

urlpatterns = [
	path("", views.bids_list, name="bids_list"),
	path("add/", views.add_bid, name="add_bid"),
	path("<int:bid_id>/", views.view_bid, name="view_bid"),
	path("<int:bid_id>/status/<str:status>/", views.set_bid_status, name="set_bid_status"),
	path("<int:bid_id>/edit/", views.edit_bid, name="edit_bid"),
]
