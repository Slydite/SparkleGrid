from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .models import MeasurementsOne, MeasurementsTwo, MeasurementsFive, MeasurementsThree, MeasurementsFour, MeasurementsSix
import datetime
import logging

@csrf_exempt
def hello_world(request):
    return HttpResponse("hello world")

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
        
        
        
        
    
