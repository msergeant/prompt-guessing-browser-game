from django.db import models


class Image(models.Model):
    caption = models.CharField(default="", max_length=50)
    file = models.FileField(upload_to='images')
    created = models.DateTimeField(auto_now_add=True)
