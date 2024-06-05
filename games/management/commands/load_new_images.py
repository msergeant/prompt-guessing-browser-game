import hashlib
import os

from django.core.files.images import ImageFile
from django.core.management.base import BaseCommand
from images.models import Image


class Command(BaseCommand):

    help = "Load new images for use in games"

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            type=str,
            help='path')

    def handle(self, *args, **options):
        image_path = options['path']

        for img in os.listdir(image_path):
            caption = img[0:-6].replace('_', ' ').upper()
            with open(os.path.join(image_path, img), 'rb') as file:
                Image.objects.create(
                    caption=caption,
                    file=ImageFile(
                        file, name=hashlib.md5(img.encode()).hexdigest()
                        + img[-4:]))
