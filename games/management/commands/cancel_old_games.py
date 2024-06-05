import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import timezone
from games.models import Game, GameStatus


class Command(BaseCommand):

    help = "Cancel games that are more than 24 hours old"

    def handle(self, *args, **options):
        old_games = Game.objects.filter(status=GameStatus.STARTING,
                                        created__lte=timezone.now() - dt.timedelta(days=1))
        for game in old_games:
            game.scoring_results['status'] = f"Cancelled by cron: {timezone.now().isoformat()}"
            game.status = GameStatus.ABANDONED
            game.save()
