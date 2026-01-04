"""
URL configuration for jambas project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView
from django.templatetags.static import static as static_url

admin.site.site_header = "Backend Engine"
admin.site.site_title = "Backend Engine"
admin.site.index_title = "Backend Engine"

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url=static_url("images/favicon.png"), permanent=False)),
    path('admin/', admin.site.urls),
    path('api/', include('jambas.api_urls')),
    # Frontend (Django templates) – keep routes un-namespaced for simple `{% url 'clients' %}` usage
    path('', include('core.urls')),
    path('bids/', include('bids.urls')),
    path('documents/', include('documents.urls')),
    path('accounts/', include(('accounts.urls', 'accounts'), namespace='accounts')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
