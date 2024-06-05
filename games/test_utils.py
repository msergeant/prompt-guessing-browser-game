import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase
from images.models import Image

from games.models import Game, Player
from games.utils import finished_game_context


class UtilsTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(UtilsTestCase, cls).setUpClass()
        cls.player1 = Player.objects.create(nickname="P1")
        cls.player2 = Player.objects.create(nickname="P2")
        cls.game = Game.objects.create(owner=cls.player1,
                                       scoring_results={'round_totals': {}})
        cls.game.players.add(cls.player1)
        cls.game.players.add(cls.player2)

        for i in range(5):
            content_file = ContentFile("not a real image",
                                       name=f"image{i}")
            image = Image.objects.create(file=content_file,
                                         caption=f"image {i} title")
            rownd = cls.game.rounds.create(order=i + 1, image=image)
            rownd.guesses.create(player=None, text=image.caption)
            rownd.guesses.create(player=cls.player1, text=f"Player 1 guess {i+1}")
            rownd.guesses.create(player=cls.player2, text=f"Player 2 guess {i+1}")

    @classmethod
    def tearDownClass(cls):
        super(UtilsTestCase, cls).tearDownClass()
        img_dir = os.path.join(settings.MEDIA_ROOT, "images")
        for f in os.listdir(img_dir):
            if f.startswith("image"):
                os.remove(os.path.join(img_dir, f))

    def test_single_best_vote_getter(self):
        rownd = self.game.rounds.get(order=3)
        guess = rownd.guesses.exclude(player=None).get(player=self.player1)
        guess.votes.create(player=self.player2)

        result = finished_game_context(self.game, self.player1)
        self.assertEqual(result.get('best_answers'), [{'votes': 1,
                                                       'guesser': 'P1',
                                                       'caption': 'Player 1 guess 3',
                                                       'img_src': rownd.image.file.url}])

    def test_multiple_best_vote_getter(self):
        rownd3 = self.game.rounds.get(order=3)
        guess = rownd3.guesses.exclude(player=None).get(player=self.player1)
        guess.votes.create(player=self.player2)
        guess.votes.create(player=self.player1)

        rownd4 = self.game.rounds.get(order=4)
        guess = rownd4.guesses.exclude(player=None).get(player=self.player2)
        guess.votes.create(player=self.player1)

        result = finished_game_context(self.game, self.player1)
        self.assertEqual(result.get('best_answers'), [{'votes': 2,
                                                       'guesser': 'P1',
                                                       'caption': 'Player 1 guess 3',
                                                       'img_src': rownd3.image.file.url},
                                                      {'votes': 1,
                                                       'guesser': 'P2',
                                                       'caption': 'Player 2 guess 4',
                                                       'img_src': rownd4.image.file.url}])

    def test_hardest_prompt(self):
        rownd = self.game.rounds.get(order=3)
        for r in self.game.rounds.exclude(id=rownd.id).all():
            guess = r.guesses.filter(player=None).first()
            guess.votes.create(player=self.player2)

        result = finished_game_context(self.game, self.player1)
        self.assertEqual(result.get('hardest_prompt'), {'votes': 0,
                                                        'guesser': None,
                                                        'caption': rownd.image.caption,
                                                        'img_src': rownd.image.file.url})

    def test_easiest_prompt(self):
        rownd = self.game.rounds.get(order=3)
        guess = rownd.guesses.filter(player=None).first()
        guess.votes.create(player=self.player2)

        result = finished_game_context(self.game, self.player1)
        self.assertEqual(result.get('easiest_prompt'), {'votes': 1,
                                                        'guesser': None,
                                                        'caption': rownd.image.caption,
                                                        'img_src': rownd.image.file.url})

    def test_easiest_prompt_is_empty(self):
        result = finished_game_context(self.game, self.player1)
        self.assertEqual(result.get('easiest_prompt'), None)
