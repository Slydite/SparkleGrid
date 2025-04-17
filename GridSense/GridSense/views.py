from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .models import MeasurementsOne, MeasurementsTwo, MeasurementsFive, MeasurementsThree, MeasurementsFour, MeasurementsSix
import datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializer import MeasurementsOneSerializer,MeasurementsTwoSerializer,MeasurementsThreeSerializer,MeasurementsFourSerializer,MeasurementsFiveSerializer,MeasurementsSixSerializer
from django.utils.timezone import now, timedelta
import requests


@api_view(['POST'])
def push_to_cloud(request,sensor_id):
    model_mapping = {
            1: MeasurementsOne,
            2: MeasurementsTwo,
            3: MeasurementsThree,
            4: MeasurementsFour,
            5: MeasurementsFive,
            6: MeasurementsSix
        }
    serializer_mapping = {
            1: MeasurementsOneSerializer,
            2: MeasurementsTwoSerializer,
            3: MeasurementsThreeSerializer,
            4: MeasurementsFourSerializer,
            5: MeasurementsFiveSerializer,
            6: MeasurementsSixSerializer
        }
    db_number=0
    current_time=datetime.datetime.now()
    print(current_time)
 
    current_hour = current_time.time()
    print(current_hour)

    time_list=[datetime.time(0, 0) , datetime.time(4, 0), datetime.time(8, 0),
               datetime.time(12, 0),datetime.time(16, 0),
               datetime.time(20, 0)]

   
    # Check if current time is within the range
    if time_list[0] <= current_hour <= time_list[1]:
            db_number=1
    elif time_list[1] <= current_hour <= time_list[2]:
            db_number=2
    elif time_list[2] <= current_hour <= time_list[3]:
            db_number=3
    elif time_list[3] <= current_hour <= time_list[4]:
            db_number=6
    elif time_list[4] <= current_hour <= time_list[5]:
            db_number=5
    elif time_list[5] <= current_hour <= time_list[0]:
            db_number=6
    else:
        return JsonResponse({'error': 'Error in Execution'}, status=400)

    current_db=model_mapping[db_number]
    current_serializer=serializer_mapping[db_number]
    
    data = current_db.objects.filter(
        
        sensor_id=sensor_id
    ).order_by('-time')[:300]


    serializer = current_serializer(data, many=True)
    
    try:
        response = requests.post(
            'https://your-cloud.com/api/receive-data/',
            json=serializer.data,
            timeout=10
        )
        if response.status_code == 200:
            return Response({'status': 'success', 'cloud_response': response.json()})
        else:
            return Response({'status': 'failed', 'cloud_status': response.status_code})
    except Exception as e:
        return Response({'status': 'error', 'detail': str(e)}, status=500)



@csrf_exempt
def measurements_by_sensor_id(request, table_no, sensor_id):
    if request.method == 'GET':
        model_mapping = {
            1: MeasurementsOne,
            2: MeasurementsTwo,
            3: MeasurementsThree,
            4: MeasurementsFour,
            5: MeasurementsFive,
            6: MeasurementsSix
        }
        if table_no in model_mapping:
            model_class = model_mapping[table_no]
            latest_measurement = model_class.objects.filter(sensor_id=sensor_id).order_by('-time').first()
            if latest_measurement:
                data = {
                    'sensdata': latest_measurement.sensdata,
                    'time': latest_measurement.time,
                    'rms': latest_measurement.rmsvalue,
                    'pf': latest_measurement.pf,
                    'thd': latest_measurement.thd,
                    'sname': latest_measurement.sname,
                    'stype': latest_measurement.stype,
                }
                return JsonResponse({'measurements': data})
            else:
                return JsonResponse({'error': 'No measurements found'}, status=404)
        else:
            return JsonResponse({'error': 'Invalid parameters'}, status=400)
        
def measurements_by_time(request, sensor_id):
    model_mapping = {
            1: MeasurementsOne,
            2: MeasurementsTwo,
            3: MeasurementsThree,
            4: MeasurementsFour,
            5: MeasurementsFive,
            6: MeasurementsSix
        }
    db_number=0
    current_time=datetime.datetime.now()
    print(current_time)
 
    current_hour = current_time.time()
    print(current_hour)

    time_list=[datetime.time(0, 0) , datetime.time(4, 0), datetime.time(8, 0),
               datetime.time(12, 0),datetime.time(16, 0),
               datetime.time(20, 0)]

   
    # Check if current time is within the range
    if time_list[0] <= current_hour <= time_list[1]:
            db_number=1
    elif time_list[1] <= current_hour <= time_list[2]:
            db_number=2
    elif time_list[2] <= current_hour <= time_list[3]:
            db_number=3
    elif time_list[3] <= current_hour <= time_list[4]:
            db_number=6
    elif time_list[4] <= current_hour <= time_list[5]:
            db_number=5
    elif time_list[5] <= current_hour <= time_list[0]:
            db_number=6
    else:
        return JsonResponse({'error': 'Error in Execution'}, status=400)
    if db_number in model_mapping:
            print(db_number)
            model_class = model_mapping[db_number]
            latest_measurement = model_class.objects.filter(sensor_id=sensor_id).order_by('-time').first()
            if latest_measurement:
                data = {
                    'sensdata': latest_measurement.sensdata,
                    'time': latest_measurement.time,
                    'rms': latest_measurement.rmsvalue,
                    'pf': latest_measurement.pf,
                    'thd': latest_measurement.thd,
                    'sname': latest_measurement.sname,
                    'stype': latest_measurement.stype,
                }
                return JsonResponse({'measurements': data})
            else:
                return JsonResponse({'error': 'No measurements found'}, status=404)
        
        
        
        
    
