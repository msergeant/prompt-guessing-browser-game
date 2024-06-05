import datetime as dt
import random

from celery import Celery
from django.conf import settings
from django.utils import timezone
from images.models import Image

from games.models import Game, GameStatus, Vote

from .utils import guesses_with_votes, send_channel_message, status

GUESS_TIME = 60
VOTE_TIME = 30
ROUNDS = 5


app = Celery('games.engine', broker=settings.REDIS_URL)


def _get_image_ids(game):
    recent_games = (Game.objects
                    .filter(status=GameStatus.COMPLETE,
                            players__in=game.players.all())
                    .order_by('-created'))
    recent_images = recent_games.values_list('rounds__image__id', flat=True)
    ids = list(Image.objects
               .exclude(pk__in=recent_images)
               .values_list('pk', flat=True))
    if len(ids) < ROUNDS:
        extras = list(Image.objects
                      .exclude(pk__in=ids)
                      .values_list('pk', flat=True))
        extras = random.sample(extras, ROUNDS - len(ids))
        ids = extras + ids

    return random.sample(ids, ROUNDS)


def start_game(game, continue_timer=True):
    game.status = GameStatus.GUESSING_ONE
    game.next_update = timezone.now() + dt.timedelta(seconds=GUESS_TIME)

    random_image_ids = _get_image_ids(game)
    for i, id in enumerate(random_image_ids):
        image = Image.objects.get(pk=id)
        rownd = game.rounds.create(order=i + 1, image=image)
        rownd.guesses.create(player=None, text=image.caption)

    player_list = {p.id: p.nickname for p in game.players.all()}
    game.scoring_results = {
        'players': player_list,
        'round_totals': {}
    }

    game.save()

    if continue_timer:
        timer_tick.delay(game.id)


def guessing_update(game, ready_for_transition):
    round_number = int(game.status[1])
    rownd = game.rounds.get(order=round_number)
    all_players_guessed = rownd.guesses.count() == game.players.count() + 1

    if all_players_guessed or ready_for_transition:
        game.status = 'V' + game.status[1]
        game.next_update = timezone.now() + dt.timedelta(seconds=VOTE_TIME)
        game.save()

        return True


def voting_update(game, ready_for_transition):
    round_number = int(game.status[1])
    rownd = game.rounds.get(order=round_number)
    all_players_voted = (Vote.objects.filter(guess__rownd=rownd).count() ==
                         game.players.count())

    if all_players_voted or ready_for_transition:
        game.status = 'S' + game.status[1]
        game.reveal_step = 1
        game.save()

        return True


def compute_score(rownd, game):
    round_scores = {p.id: 0 for p in game.players.all()}

    correct_guess = rownd.guesses.filter(player=None).first()

    for player in game.players.all():
        if correct_guess.votes.filter(player=player).exists():
            round_scores[player.id] += 2

    for guess in guesses_with_votes(rownd):
        round_scores[guess.player.id] += guess.votes.count()

    game.scoring_results['round_totals'][rownd.order] = round_scores
    game.save()


def revealing_update(game):
    round_number = int(game.status[1])
    rownd = game.rounds.get(order=round_number)

    if game.reveal_step == 1:
        compute_score(rownd, game)

    guesses = guesses_with_votes(rownd)
    if game.reveal_step >= 99:
        game.status = 'R' + str(round_number + 1)
        game.next_update = (timezone.now() +
                            dt.timedelta(seconds=GUESS_TIME))
    elif game.reveal_step > guesses.count():
        game.reveal_step = 98
        if round_number >= ROUNDS:
            game.status = GameStatus.COMPLETE

    game.reveal_step += 1
    game.save()
    return True


@app.task
def timer_tick(game_id):
    game = Game.objects.get(pk=game_id)

    _status = status(game)
    tick_delay = None
    if _status == 'registering':
        start_game(game)
        seconds_remaining = (game.next_update - timezone.now()).total_seconds()

        send_channel_message(game.code, {"type": "refresh_game_content"})
    else:
        seconds_remaining = round((game.next_update - timezone.now())
                                  .total_seconds())
        ready_for_transition = seconds_remaining <= 0

        status_change = False
        if _status == 'guessing':
            tick_delay = 1
            status_change = guessing_update(game, ready_for_transition)
        elif _status == 'voting':
            status_change = voting_update(game, ready_for_transition)
            tick_delay = 5 if status_change else 1
            if status_change:
                seconds_remaining = ""
        elif _status == 'revealing':
            status_change = revealing_update(game)
            seconds_remaining = ""

            if game.status != GameStatus.COMPLETE:
                tick_delay = 5

        if status_change:
            send_channel_message(game.code, {"type": "refresh_game_content"})

    send_channel_message(game.code, {"type": "countdown_update",
                                     "remaining": seconds_remaining})

    if tick_delay:
        timer_tick.apply_async(args=[game.id], countdown=tick_delay)
