import datetime as dt

from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from games.models import Game, GameStatus, Guess, Player


# Register your models here.
@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['code', 'created', 'owner', 'status']
    list_filter = ['status']
    search_fields = ['code', 'owner__nickname']
    date_hierarchy = "created"

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [path("stats/", self.admin_site.admin_view(self.stats))]
        return my_urls + urls

    def stats(self, request):
        date = request.GET.get('date', None)
        if date:
            date = parse_datetime(date).date()
        date = date or timezone.now().date()
        next_date = date + dt.timedelta(days=1)
        previous_date = date - dt.timedelta(days=1)

        games_with_late_guesses = (Guess.objects
                                   .exclude(player=None)
                                   .filter(rownd__order=5,
                                           rownd__game__created__gte=date,
                                           rownd__game__created__lt=next_date)
                                   .values_list('rownd__game__id', flat=True))
        games = [(f"<a href=\"/admin/games/game/{game.id}/change\" target=\"_blank\">{game.code}</a>",
                  f"<a href=\"/game-summary/{game.id}/\" target=\"_blank\">View</a>",
                  timezone.localtime(game.created).strftime('%Y-%m-%d %I:%M:%S %p %Z'),
                  game.owner) for game in Game.objects.filter(id__in=games_with_late_guesses)]

        data = dict(
            self.admin_site.each_context(request),
            date=date,
            games_today=Game.objects.filter(created__gte=date,
                                            created__lt=next_date).count(),
            completed_games_today=Game.objects.filter(created__gte=date,
                                                      created__lt=next_date,
                                                      status=GameStatus.COMPLETE).count(),
            legit_completed=len(games),
            link_next=f"/admin/games/game/stats/?date={next_date.isoformat()}",
            link_previous=f"/admin/games/game/stats/?date={previous_date.isoformat()}",
            games=games,
        )

        return TemplateResponse(request, 'admin/stats.html', context=data)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['nickname', 'anonymous_user_id', 'user', 'created']
