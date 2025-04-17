from django.db import models
from django.contrib.postgres.fields import ArrayField

class NestedDecimalArrayField(ArrayField):
    def __init__(self, *args, **kwargs):
        kwargs['base_field'] = ArrayField(models.DecimalField(max_digits=5, decimal_places=2), size=2)
        super().__init__(*args, **kwargs)

class Aggregate_data(models.Model):
    sensor_id = models.PositiveIntegerField()
    
    time = models.DateTimeField(auto_now_add=True)
    rmsvalue = models.DecimalField(max_digits=5, decimal_places=2)
    pf = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Power Factor')
    thd = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='Total Harmonic Distortion')
    sname = models.CharField(max_length=50, verbose_name='Sensor Name')
    stype = models.CharField(max_length=50, verbose_name='Sensor Type', choices=[('Current', 'Current'), ('Voltage', 'Voltage')])

    class Meta:
        abstract = True
        db_table = 'Aggregate_db'


