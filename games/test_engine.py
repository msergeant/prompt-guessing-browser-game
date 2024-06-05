import datetime as dt
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from images.models import Image

from games.engine import (compute_score, guessing_update, revealing_update,
                          start_game, voting_update)
from games.models import Game, GameStatus, Player, Round


class EngineTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(EngineTestCase, cls).setUpClass()
        player = Player.objects.create(nickname="Owner")
        cls.game = Game.objects.create(owner=player)
        cls.game.players.add(player)

        for i in range(6):
            content_file = ContentFile("not a real image",
                                       name=f"image{i}")
            Image.objects.create(file=content_file,
                                 caption=f"image {i} title")

    @classmethod
    def tearDownClass(cls):
        super(EngineTestCase, cls).tearDownClass()
        img_dir = os.path.join(settings.MEDIA_ROOT, "images")
        for f in os.listdir(img_dir):
            if f.startswith("image"):
                os.remove(os.path.join(img_dir, f))

    def test_start_game_sets_status(self):
        start_game(self.game, continue_timer=False)
        self.assertEqual(self.game.status, GameStatus.GUESSING_ONE)
        self.assertAlmostEqual(self.game.next_update,
                               timezone.now() + dt.timedelta(seconds=60),
                               delta=dt.timedelta(seconds=1))

    def test_start_game_creates_rounds(self):
        start_game(self.game, continue_timer=False)

        round_numbers = list(self.game.rounds
                             .order_by('order')
                             .values_list('order', flat=True))
        self.assertEqual(round_numbers, [1, 2, 3, 4, 5])
        unique_images = self.game.rounds.values_list('image_id', flat=True)

        self.assertEqual(len(set(unique_images)), 5)

    def test_start_game_adds_nicknames_to_scoring_results(self):
        start_game(self.game, continue_timer=False)

        results = self.game.scoring_results
        for player in self.game.players.all():
            self.assertEqual(results['players'][player.id],
                             player.nickname)

    def test_guessing_update_when_not_enough_votes(self):
        self.game.status = GameStatus.GUESSING_THREE
        self.game.rounds.create(order=3, image=Image.objects.first())
        result = guessing_update(self.game, False)

        self.assertFalse(result)
        self.assertEqual(self.game.status, GameStatus.GUESSING_THREE)

    def test_guessing_update_when_guesses_are_in(self):
        self.game.status = GameStatus.GUESSING_THREE
        r = self.game.rounds.create(order=3, image=Image.objects.first())
        r.guesses.create(player=self.game.owner, text="My Guess")
        r.guesses.create(text="Real Guess")
        result = guessing_update(self.game, False)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.VOTING_THREE)

    def test_guessing_update_when_ready_for_update(self):
        self.game.status = GameStatus.GUESSING_THREE
        self.game.rounds.create(order=3, image=Image.objects.first())
        result = voting_update(self.game, True)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.REVEAL_THREE)

    def test_voting_update_when_not_enough_votes(self):
        self.game.status = GameStatus.VOTING_THREE
        self.game.rounds.create(order=3, image=Image.objects.first())
        result = voting_update(self.game, False)

        self.assertFalse(result)
        self.assertEqual(self.game.status, GameStatus.VOTING_THREE)

    def test_voting_update_when_votes_are_in(self):
        self.game.status = GameStatus.VOTING_THREE
        r = self.game.rounds.create(order=3, image=Image.objects.first())
        r.guesses.create(player=self.game.owner, text="My Guess")
        g = r.guesses.create(text="Real Guess")
        g.votes.create(player=self.game.owner)
        result = voting_update(self.game, False)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.REVEAL_THREE)

    def test_voting_update_when_ready_for_update(self):
        self.game.status = GameStatus.VOTING_THREE
        self.game.rounds.create(order=3, image=Image.objects.first())
        result = voting_update(self.game, True)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.REVEAL_THREE)


class RoundRevealTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        host = Player.objects.create(nickname='host')
        cls.game = Game.objects.create(code='ABCD',
                                       status=GameStatus.REVEAL_ONE,
                                       scoring_results={'round_totals': {}},
                                       reveal_step=1,
                                       owner=host)
        content_file = ContentFile("not a real image",
                                   name="image")
        i = Image.objects.create(file=content_file,
                                 caption="image title")
        cls.rownd = Round.objects.create(game=cls.game, order=1, image=i)

        cls.players = []

        guesses = [cls.rownd.guesses.create(player=None, text=i.caption)]
        for i in range(5):
            cls.players.append(Player.objects.create(nickname=f"player{i+1}"))
            cls.game.players.add(cls.players[i])
            guesses.append(cls.rownd.guesses.create(player=cls.players[i],
                                                    text=f"guess{i+1}"))

        guesses[0].votes.create(player=cls.players[1])
        guesses[0].votes.create(player=cls.players[2])
        guesses[1].votes.create(player=cls.players[3])
        guesses[1].votes.create(player=cls.players[4])
        guesses[2].votes.create(player=cls.players[0])

    def test_revealing_update_stays_revealing(self):
        result = revealing_update(self.game)
        self.assertEqual(self.game.reveal_step, 2)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.REVEAL_ONE)

    def test_revealing_update_transitions_to_show_score(self):
        self.game.reveal_step = 4
        result = revealing_update(self.game)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.REVEAL_ONE)
        self.assertEqual(self.game.reveal_step, 99)

    def test_revealing_update_transitions_to_guessing(self):
        self.game.reveal_step = 99
        result = revealing_update(self.game)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.GUESSING_TWO)
        self.assertAlmostEqual(self.game.next_update,
                               timezone.now() + dt.timedelta(seconds=60),
                               delta=dt.timedelta(seconds=1))

    def test_revealing_update_transitions_to_finished(self):
        self.game.reveal_step = 6
        self.game.status = GameStatus.REVEAL_FIVE

        self.rownd.order = 5
        self.rownd.save()

        result = revealing_update(self.game)

        self.assertTrue(result)
        self.assertEqual(self.game.status, GameStatus.COMPLETE)


class ScoringTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        host = Player.objects.create(nickname='host')
        cls.game = Game.objects.create(code='ABCD',
                                       status=GameStatus.REVEAL_ONE,
                                       scoring_results={'round_totals': {}},
                                       reveal_step=1,
                                       owner=host)
        content_file = ContentFile("not a real image",
                                   name="image")
        i = Image.objects.create(file=content_file,
                                 caption="image title")
        cls.rownd = Round.objects.create(game=cls.game, order=1, image=i)

        cls.players = []

        guesses = [cls.rownd.guesses.create(player=None, text=i.caption)]
        for i in range(5):
            cls.players.append(Player.objects.create(nickname=f"player{i+1}"))
            cls.game.players.add(cls.players[i])
            guesses.append(cls.rownd.guesses.create(player=cls.players[i],
                                                    text=f"guess{i+1}"))

    def test_voting_for_correct_image(self):
        player = self.players[0]
        guess = self.rownd.guesses.filter(
            text=self.rownd.image.caption).first()
        guess.votes.create(player=player)

        compute_score(self.rownd, self.game)

        self.assertEqual(
            self.game
            .scoring_results
            .get('round_totals', {})
            .get(self.rownd.order, {})
            .get(player.id, 0), 2)

        for other in self.players:
            if other != player:
                self.assertEqual(
                    self.game
                    .scoring_results
                    .get('round_totals')
                    .get(self.rownd.order)
                    .get(other.id), 0)

    def test_receiving_votes_from_other_players(self):
        player = self.players[0]
        other = self.players[1]
        guess = self.rownd.guesses.filter(player=player).first()
        guess.votes.create(player=other)

        compute_score(self.rownd, self.game)

        self.assertEqual(
            self.game
            .scoring_results
            .get('round_totals', {})
            .get(self.rownd.order, {})
            .get(player.id, 0), 1)

        for other in self.players:
            if other != player:
                self.assertEqual(
                    self.game
                    .scoring_results
                    .get('round_totals')
                    .get(self.rownd.order)
                    .get(other.id), 0)
