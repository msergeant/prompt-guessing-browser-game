import uuid

from django.core.management.base import BaseCommand
from games.engine import compute_score
from games.models import Game, GameStatus, Player
from images.models import Image


class Command(BaseCommand):

    help = "Seed some games for development purposes"

    def _init_game(self, game, players):
        for player in players:
            game.players.add(player)

        for i in range(5):
            image = Image.objects.get(pk=i + 1)
            rownd = game.rounds.create(order=i + 1, image=image)
            rownd.guesses.create(player=None, text=image.caption)

        player_list = {p.id: p.nickname for p in game.players.all()}
        game.scoring_results = {
            'players': player_list,
            'round_totals': {}
        }
        game.save()

        guesses = []
        rownd = game.rounds.get(order=1)
        if game.status not in [GameStatus.STARTING, GameStatus.GUESSING_ONE]:
            for player in players:
                guesses.append(
                    rownd.guesses.create(player=player,
                                         text=f"{player.nickname}'s try"))

        correct_guess = rownd.guesses.get(player=None)
        if game.status not in [GameStatus.STARTING, GameStatus.GUESSING_ONE,
                               GameStatus.VOTING_ONE]:
            for i, player in enumerate(players):
                if i % 2 == 0:
                    correct_guess.votes.create(player=player)
                else:
                    guesses[0].votes.create(player=player)

            compute_score(rownd, game)

    def handle(self, *args, **options):
        players = []
        for i in range(3):
            uid = uuid.UUID(f'00000000-0000-0000-0000-00000000000{i}')
            p, _ = Player.objects.get_or_create(nickname=f"Dev Player {i + 1}",
                                                anonymous_user_id=uid)
            players.append(p)

        games = [
            ('START', GameStatus.STARTING, 1),
            ('GUESS', GameStatus.GUESSING_ONE, 1),
            ('VOTES', GameStatus.VOTING_ONE, 1),
            ('REVL1', GameStatus.REVEAL_ONE, 1),
            ('REVL2', GameStatus.REVEAL_ONE, 2),
            ('REVL3', GameStatus.REVEAL_ONE, 99),
            ('CMPLT', GameStatus.COMPLETE, 1),
        ]

        for code, status, step in games:
            game = Game.objects.create(
                code=code, status=status, reveal_step=step, owner=players[0])
            self._init_game(game, players)

        print("Seed games created.")
        print("Visit /games/dev_pages/ to start devving")
