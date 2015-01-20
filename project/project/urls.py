from django.conf.urls import include, url
from django.contrib import admin

import apps.phone.views
import apps.upload.views
import apps.image.views

urlpatterns = [
    # Examples:
    # url(r'^$', 'project.views.home', name='home'),
    # url(r'^blog/', include('blog.urls')),

    url(r'^admin/', include(admin.site.urls)),

    url(r'^login/$', apps.phone.views.login),
    url(r'^callback/foreground-done/$', apps.upload.views.callback_foreground),
    url(r'^callback/background-done/$', apps.upload.views.callback_background),


    url(r'^foreground/hot/$', apps.image.views.ImageGetter.as_view()),
    url(r'^foreground/new/$', apps.image.views.ImageGetter.as_view()),
    url(r'^background/hot/$', apps.image.views.ImageGetter.as_view()),
    url(r'^background/new/$', apps.image.views.ImageGetter.as_view()),

    url(r'^foreground/category/$', apps.image.views.get_foregound_category)
]
