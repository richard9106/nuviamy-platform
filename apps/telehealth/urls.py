from django.urls import path
from .views import VideoRoomView, VideoActionView
app_name = 'telehealth'
urlpatterns = [path('<int:pk>/', VideoRoomView.as_view(), name='room'),
               path('<int:pk>/action/', VideoActionView.as_view(), name='action')]
