# from django.contrib import admin
# from django.urls import path, include
# from graphene_django.views import GraphQLView
# from django.views.decorators.csrf import csrf_exempt
# from GridSense.schema import schema # Updated app name
# from GridSense.views import measurements_by_sensor_id

# urlpatterns = [
#     path('admin/', admin.site.urls),
    
#     # path('gridsense_app/', include('GridSense.urls')), # Updated to gridsense_app, assuming you might want to rename app urls path
#     path('measurements/<int:table_no>/<int:sensor_id>/', measurements_by_sensor_id, name='measurements_by_sensor_id'),
# ]

# /home/mgrid/development/microgrid-iot/GridSense/GridSense/urls.py
from django.contrib import admin
from django.urls import path
from GridSense.views import measurements_by_sensor_id, measurements_by_time,push_to_cloud

urlpatterns = [
    path('admin/', admin.site.urls),
    path('measurements/<int:table_no>/<int:sensor_id>/', measurements_by_sensor_id, name='measurements_by_sensor_id'),
    path('measurements/<int:sensor_id>/', measurements_by_time, name='measurements_by_time'),
    path('api/push-to-cloud/<int:sensor_id>/', push_to_cloud),
]
