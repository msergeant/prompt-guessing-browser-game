# Generated by Django 4.1.2 on 2022-11-26 17:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("images", "0001_initial"),
        ("games", "0006_player_created"),
    ]

    operations = [
        migrations.AddField(
            model_name="round",
            name="image",
            field=models.ForeignKey(
                default=0,
                on_delete=django.db.models.deletion.CASCADE,
                to="images.image",
            ),
            preserve_default=False,
        ),
    ]