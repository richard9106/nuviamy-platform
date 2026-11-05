from django.urls import path
from .views import VideoRoomView, VideoActionView
from .settings_views import VideoSettingsView
app_name = 'telehealth'
urlpatterns = [path('settings/',VideoSettingsView.as_view(),name='settings'),
               path('<int:pk>/', VideoRoomView.as_view(), name='room'),
               path('<int:pk>/action/', VideoActionView.as_view(), name='action')]
