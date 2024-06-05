import datetime as dt
import random

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .models import Game, GameStatus, Guess

NUM_TO_TEXT = {
    0: 'zero',
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
}


def send_channel_message(game_code, data):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(game_code, data)


def fetch_running_game(**query):
    return (Game.objects
            .exclude(Q(status=GameStatus.COMPLETE) |
                     Q(status=GameStatus.ABANDONED))
            .filter(**query).first())


def fetch_recent_game(**query):
    return (Game.objects
            .filter(status=GameStatus.COMPLETE,
                    created__gte=timezone.now() - dt.timedelta(days=1))
            .filter(**query).order_by("-created").first())


def status(game):
    if game.status == GameStatus.STARTING:
        return 'registering'
    elif game.status.startswith('R'):
        return 'guessing'
    elif game.status.startswith('V'):
        return 'voting'
    elif game.status.startswith('S'):
        return 'revealing'
    elif game.status == GameStatus.COMPLETE:
        return 'complete'


def guesses_with_votes(rownd):
    return (rownd.guesses
            .exclude(player=None)
            .annotate(vote_count=Count('votes'))
            .filter(vote_count__gt=0)
            .order_by('vote_count'))


def _reveal_data(rownd, step):
    guesses = guesses_with_votes(rownd)

    if step > guesses.count():
        guess = rownd.guesses.filter(player=None).first()
        correct = True
    else:
        guess = guesses[step - 1]
        correct = False

    vote_count = guess.votes.count()
    vote_text = f"{vote_count} Vote"
    if vote_count != 1:
        vote_text += 's'

    return {
        'text': guess.text,
        'players': enumerate([v.player.nickname for v in guess.votes.all()]),
        'vote_text': vote_text,
        'correct': correct,
        'submitter': guess.player and guess.player.nickname,
    }


def _scoreboard(game):
    totals = {p.id: {'name': p.nickname,
                     'score': 0} for p in game.players.all()}

    for r, scores in game.scoring_results.get('round_totals').items():
        for id, s in scores.items():
            totals[int(id)]['score'] += s

    scores = sorted(set(x['score'] for x in totals.values()), reverse=True)
    for player in totals.values():
        player['place'] = scores.index(player['score']) + 1
        if player['place'] == 1:
            player['color'] = 'bg-yellow-400'
        if player['place'] == 2:
            player['color'] = 'bg-gray-400 text-white'
        if player['place'] == 3:
            player['color'] = 'bg-yellow-900 text-white'

    totals_list = [v for k, v in totals.items()]
    return sorted(totals_list, key=lambda x: x['score'], reverse=True)


def _random_guess_order(rownd, player):
    guesses = list(rownd.guesses.exclude(player=player).all())

    random.seed(player.id + rownd.id)
    random.shuffle(guesses)

    return guesses


def cdnify(filename):
    return f"{ settings.CDN_BASE_URL }{filename}"


def finished_game_context(game, current_player):
    _status = status(game)

    top_guesses = [{'votes': g.vote_count,
                    'guesser': g.player.nickname,
                    'img_src': cdnify(g.rownd.image.file.name),
                    'caption': g.text}
                   for g in (Guess.objects
                             .annotate(vote_count=Count('votes'))
                             .filter(rownd__game=game, vote_count__gt=0)
                             .exclude(player=None)
                             .order_by('-vote_count')
                             .all())][0:3]

    hardest_guess = (Guess.objects
                     .annotate(vote_count=Count('votes'))
                     .filter(player=None, rownd__game=game)
                     .order_by('vote_count')
                     .first())
    hardest_prompt = hardest_guess and {'votes': hardest_guess.vote_count,
                                        'guesser': None,
                                        'img_src': cdnify(hardest_guess.rownd.image.file.name),
                                        'caption': hardest_guess.text}

    easiest_guess = (Guess.objects
                     .annotate(vote_count=Count('votes'))
                     .filter(player=None, rownd__game=game, vote_count__gt=0)
                     .order_by('-vote_count')
                     .first())

    easiest_prompt = easiest_guess and {'votes': easiest_guess.vote_count,
                                        'guesser': None,
                                        'img_src': cdnify(easiest_guess.rownd.image.file.name),
                                        'caption': easiest_guess.text}

    return {"status": _status,
            "code": game.code,
            "title": "Final Score",
            "is_owner": game.owner == current_player,
            "is_closed": game.closed,
            "scoreboard": _scoreboard(game),
            "best_answers": top_guesses,
            "hardest_prompt": hardest_prompt,
            "easiest_prompt": easiest_prompt}


def running_game_context(game, current_player):
    _status = status(game)

    if _status == 'complete':
        return finished_game_context(game, current_player)

    rownd = int(game.status[1])

    rownd = game.rounds.filter(order=rownd).first()
    rownd_id = rownd and rownd.id
    already_guessed = rownd and rownd.guesses.filter(
        player=current_player).exists()
    already_voted = rownd and rownd.guesses.filter(
        votes__player=current_player).exists()
    _status = status(game)

    return {
        "rownd_id": rownd_id,
        "img_src": rownd_id and cdnify(rownd.image.file.name),
        "already_guessed": already_guessed,
        "already_voted": already_voted,
        "round_title": rownd and NUM_TO_TEXT.get(rownd.order, "").upper(),
        "status": _status,
        "round_guesses": (_status == 'voting' and
                          _random_guess_order(rownd, current_player)),
        "reveal_data": (_status == 'revealing' and
                        _reveal_data(rownd, game.reveal_step)),
        "show_scoreboard": game.reveal_step >= 99,
        "show_keyboard": _status == 'guessing' and not already_guessed,
        "scoreboard": (_status == 'revealing' and game.reveal_step >= 99 and
                       _scoreboard(game))
    }
