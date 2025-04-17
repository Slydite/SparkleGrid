from rest_framework import serializers
from .models import MeasurementsOne, MeasurementsTwo,MeasurementsThree,MeasurementsFour,MeasurementsFive,MeasurementsSix

class MeasurementsOneSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsOne
        fields = '__all__'

class MeasurementsTwoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsTwo
        fields = '__all__'


class MeasurementsThreeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsThree
        fields = '__all__'


class MeasurementsFourSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsFour
        fields = '__all__'


class MeasurementsFiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsFive
        fields = '__all__'

class MeasurementsSixSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementsSix
        fields = '__all__'

