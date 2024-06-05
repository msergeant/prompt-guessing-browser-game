import datetime as dt
import random
import string

from django.conf import settings
from django.contrib import messages
from django.db.models.functions import Length
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import loader
from django.utils import timezone

from .engine import timer_tick
from .forms import GameForm, GuessForm, JoinForm, VoteForm
from .models import Game, GameStatus, Guess, Player, Round
from .utils import (NUM_TO_TEXT, cdnify, fetch_recent_game, fetch_running_game,
                    running_game_context, send_channel_message, status)

FULL_GAME = 8


def index(request):
    template = loader.get_template('index.html')
    player = _get_player(request, False)
    existing_game = player and fetch_running_game(players=player)
    context = {
        'player_name': (player and player.nickname) or "",
        "join_button": "Join a game",
        "existing_game_code": (existing_game and existing_game.code),
        "show_howto": True,
        "include_ga": settings.ENVIRONMENT == "production",
    }
    return HttpResponse(template.render(context, request))


def _get_player(request, create=True):
    if request.user.is_authenticated:
        user_player = Player.objects.filter(user=request.user).first()
        if not user_player:
            user_player = Player.objects.create(user=request.user)

        return user_player

    id = request.COOKIES.get('player_id')

    if id:
        player = Player.objects.filter(anonymous_user_id=id).first()
        if player:
            return player

    if create:
        return Player.objects.create()


def _new_game_code():
    return ''.join(random.choice(string.ascii_letters)
                   for _ in range(4)).upper()


def _set_player_cookie(response, player):
    response.set_cookie('player_id', str(player.anonymous_user_id),
                        expires=timezone.now() + dt.timedelta(days=365))


def game_create(request):
    if request.method == 'POST':
        form = GameForm(request.POST)

        player = _get_player(request)

        if player and form.is_valid():
            code = _new_game_code()
            while fetch_running_game(code=code):
                code = _new_game_code()

            game = Game.objects.create(code=code,
                                       owner=player)
            game.players.add(player)

            player.nickname = form.data.get('nickname')
            player.save()

            response = HttpResponseRedirect(
                f"/games/play/?code={game.code}")
            _set_player_cookie(response, player)
            return response
        else:
            print("We're in the else", player, form.is_valid())

    return HttpResponse(status=404)


def _unknown_game(request):
    template = loader.get_template('unknown_game.html')

    return HttpResponse(template.render({'join_button': "Join",
                                         'show_howto': True}, request))


def show_game(request):
    code = request.GET.get('code', None)

    if code:
        game = fetch_running_game(code=code.upper())

        current_player = _get_player(request, False)

        if not game:
            recent_game = current_player and fetch_recent_game(code=code.upper(), players=current_player)
            if not recent_game:
                return _unknown_game(request)
            else:
                game = recent_game

        if game.status != GameStatus.STARTING and (current_player not in
                                                   game.players.all()):
            return _unknown_game(request)

        _status = status(game)

        warnings = messages.get_messages(request)
        duplicate_warning = ""
        for warning in warnings:
            duplicate_warning = warning.message

        players = game.players.all()
        is_registered = current_player and current_player in players
        context = {
            "current_player_id": current_player and current_player.id,
            "player_name": (current_player and current_player.nickname) or '',
            "registered": is_registered,
            "is_owner": game.owner == current_player,
            "is_closed": game.closed,
            "status": _status,
            "code": game.code,
            "owner": game.owner.nickname.upper(),
            "players": players,
            "enough_players": len(players) >= 2,
            "duplicate_warning": duplicate_warning,
            "game_full": len(players) >= FULL_GAME,
            "join_button": "Join",
            "show_howto": game.status == GameStatus.STARTING,
            "connect_code": f'ws-connect="/ws/game/{game.code}/"' if is_registered else '',
            "include_ga": settings.ENVIRONMENT == "production",
        }
        if game.status != GameStatus.STARTING:
            context = {**context, **running_game_context(game, current_player)}

        template = loader.get_template('live_game.html')

        return HttpResponse(template.render(context, request))
    else:
        return HttpResponseRedirect("/")


def join_game(request):
    if request.method == 'POST':
        form = JoinForm(request.POST)

        player = _get_player(request)

        if player and form.is_valid():
            game = Game.objects.filter(
                status=GameStatus.STARTING,
                code=form.data.get('code').upper()).first()

            if not game:
                return _unknown_game(request)

            player.nickname = form.data.get('nickname')
            player.save()

            joinable = (game.players.count() < FULL_GAME and
                        player not in game.players.all())

            if (joinable and
               game.players.filter(nickname__iexact=player.nickname).exists()):
                joinable = False
                messages.add_message(request, messages.WARNING,
                                     ("This game already has a player with "
                                      "that nickname."))

            if joinable:
                game.players.add(player)
                send_channel_message(game.code,
                                     {"type": "player_added",
                                      "player": player.nickname})

            response = HttpResponseRedirect(
                f"/games/play/?code={game.code}")
            _set_player_cookie(response, player)
            return response

    return HttpResponseRedirect("/")


def submit_guess(request):
    if request.method == 'POST':
        form = GuessForm(request.POST)

        player = _get_player(request)

        if player and form.is_valid():
            rownd = get_object_or_404(
                Round.objects.filter(pk=form.data.get('rownd_id')))

            if rownd.guesses.filter(player=player).exists():
                return HttpResponse("Only one guess allowed", status=400)

            if player not in rownd.game.players.all():
                return HttpResponse("Not in this game", status=400)

            guess = form.data.get('guess').upper()
            guess = guess.replace('\n', ' ')
            sqlized_guess = guess.replace("'", "''")

            query = f"UPPER(REPLACE(text,' ','')) = '{sqlized_guess.replace(' ', '')}'"
            if rownd.guesses.extra(where=[query]).exists():
                duplicate = True
            else:
                duplicate = False
                rownd.guesses.create(text=guess,
                                     player=player)

            template = loader.get_template('guessing.html')
            return HttpResponse(template.render(
                {"already_guessed": not duplicate,
                 "duplicate": duplicate,
                 "guess": guess,
                 "rownd_id": rownd.id,
                 "img_src": cdnify(rownd.image.file.name),
                 "round_title": NUM_TO_TEXT.get(rownd.order, "").upper()},
                request))

    return HttpResponse(status=404)


def submit_vote(request):
    if request.method == 'POST':
        form = VoteForm(request.POST)

        player = _get_player(request)

        if player and form.is_valid():
            guess = get_object_or_404(
                Guess.objects.filter(pk=form.data.get('guess_id')))

            if player not in guess.rownd.game.players.all():
                return HttpResponse("Not in this game", status=400)

            if player.vote_set.filter(guess__rownd=guess.rownd).exists():
                return HttpResponse("Only one vote allowed", status=400)

            guess.votes.create(player=player)

            rownd = guess.rownd
            template = loader.get_template('voting.html')
            return HttpResponse(template.render(
                {'already_voted': True,
                 "round_title": NUM_TO_TEXT.get(rownd.order, "").upper()},
                request))

    return HttpResponse(status=404)


def start_game_clock(request, code):
    player = _get_player(request, False)

    game = fetch_running_game(code=code, owner=player)

    if not game:
        return _unknown_game(request)

    timer_tick(game.id)

    return HttpResponse(status=200)


def reuse_game_code(request):
    if request.method == 'POST':
        owner = _get_player(request)

        code = request.POST.get('code')
        game = Game.objects.filter(code=code,
                                   status=GameStatus.COMPLETE,
                                   owner=owner).order_by('-created').first()
        if not game:
            return HttpResponse(status=404)

        new_game = Game.objects.create(
            owner=owner,
            status=GameStatus.STARTING,
            code=code)

        for player in game.players.all():
            new_game.players.add(player)

        send_channel_message(code,
                             {"type": "new_game"})
        timer_tick(new_game.id)

        response = HttpResponse(status=200)
        return response


def close_game_code(request):
    if request.method == 'POST':
        player = _get_player(request)

        code = request.POST.get('code')
        game = Game.objects.filter(code=code,
                                   status=GameStatus.COMPLETE,
                                   owner=player).order_by('-created').first()
        if not game:
            return HttpResponse(status=404)

        Game.objects.filter(code=code, status=GameStatus.COMPLETE, owner=player).update(closed=True)

        send_channel_message(code, {"type": "close_game"})

        response = HttpResponse(status=200)
        _set_player_cookie(response, player)
        return response


def cancel_game_code(request, code):
    if request.method == 'POST':
        player = _get_player(request)

        game = Game.objects.filter(code=code,
                                   status=GameStatus.STARTING,
                                   owner=player).order_by('-created').first()
        if not game:
            return HttpResponse(status=404)

        send_channel_message(code,
                             {"type": "cancel_game"})

        game.status = GameStatus.ABANDONED
        game.scoring_results['status'] = f"Cancelled by owner: {timezone.now().isoformat()}"
        game.save()

        response = HttpResponse(status=200)
        _set_player_cookie(response, player)
        return response


def dev_pages(request):
    template = loader.get_template('dev_page_index.html')
    game = Game.objects.filter(code='CMPLT').first()
    if game:
        game.created = timezone.now()
        game.save()

    uid = '00000000-0000-0000-0000-000000000000'
    player = get_object_or_404(Player.objects.filter(anonymous_user_id=uid))
    context = {
        'player': player,
        'games': Game.objects.annotate(text_len=Length('code')).filter(
            text_len=5)
    }
    response = HttpResponse(template.render(context, request))
    _set_player_cookie(response, player)
    return response


def summary(request, pk):
    if request.user.is_authenticated and request.user.is_staff:
        game = get_object_or_404(Game.objects.filter(pk=pk))
        context = running_game_context(game, _get_player(request))

        template = loader.get_template('live_game.html')

        return HttpResponse(template.render(context, request))

    return HttpResponse(status=404)
