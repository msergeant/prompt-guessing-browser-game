# Generated by Django 4.1.2 on 2022-11-27 16:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0007_round_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="reveal_step",
            field=models.IntegerField(default=1),
        ),
    ]