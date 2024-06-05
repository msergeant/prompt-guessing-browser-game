# Generated by Django 4.1.2 on 2022-11-06 00:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0002_game_players_alter_game_owner"),
    ]

    operations = [
        migrations.CreateModel(
            name="Round",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("order", models.IntegerField(default=1)),
                (
                    "game",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rounds",
                        to="games.game",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Guess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("text", models.CharField(default="", max_length=50)),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guesses",
                        to="games.player",
                    ),
                ),
                (
                    "rownd",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guesses",
                        to="games.round",
                    ),
                ),
            ],
        ),
    ]
