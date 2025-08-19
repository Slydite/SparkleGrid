from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Aggregate_data

import requests

def fetch_from_pi():
    pi_url = "http://<pi-ip>:8000/api/export-data/"  

    try:
        response = requests.get(pi_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
           
            return data
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Request failed: {e}")

def calculate_data(request):
    return



