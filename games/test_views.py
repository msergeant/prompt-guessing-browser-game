import os
import re
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.template import loader
from django.test import Client, TestCase
from django.utils import timezone
from images.models import Image

from games.engine import compute_score
from games.models import Game, GameStatus, Player, Round
from games.utils import running_game_context


def _unknown_code(self, result):
    self.assertTrue(b"Sorry, we could not find any" in result.content)
    self.assertTrue(b"Did you mean to enter a different code?"
                    in result.content)


class GameJoinTestCase(TestCase):
    def setUp(self):
        self.player = Player.objects.create(nickname="player1")

        self.password = "abc123"
        self.user = User.objects.create(username="test@test.tld")
        self.user.set_password(self.password)
        self.user.save()
        self.user_player = Player.objects.create(user=self.user)

        self.game = Game.objects.create(code='ABCD',
                                        owner=self.user_player)

        self.client = Client()

    def test_create_game_as_anonymous_user(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post('/games/create/', {'nickname': 'al'})

        self.assertTrue(Game.objects.filter(owner=self.player).exists())
        self.assertEqual(result.status_code, 302)

        self.player.refresh_from_db()
        self.assertEqual(self.player.nickname, 'al')

    def test_create_game_as_logged_in_user(self):
        self.client.login(username=self.user.username, password=self.password)
        result = self.client.post('/games/create/', {'nickname': 'al'})

        self.assertTrue(Game.objects.filter(owner=self.user_player).exists())
        self.assertEqual(result.status_code, 302)

        self.user_player.refresh_from_db()
        self.assertEqual(self.user_player.nickname, 'al')

    def test_create_game_as_unknown_user(self):
        result = self.client.post('/games/create/', {'nickname': 'al'})

        id = result.cookies.get('player_id').value
        game = Game.objects.filter(owner__anonymous_user_id=id).first()
        self.assertTrue(f"code={game.code}" in result.url)
        self.assertEqual(result.status_code, 302)

    def test_join_game_as_anonymous_user(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        with patch('games.views.send_channel_message') as send_message:
            result = self.client.post('/games/join/', {'code': self.game.code,
                                                       'nickname': 'al'})
            send_message.assert_called_with(self.game.code,
                                            {"type": "player_added",
                                             "player": "al"})

        self.assertEqual(result.status_code, 302)
        self.assertTrue(self.game in self.player.played_games.all())

        self.player.refresh_from_db()
        self.assertEqual(self.player.nickname, 'al')

    def test_join_game_code_is_not_case_sensitive(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        with patch('games.views.send_channel_message') as send_message:
            result = self.client.post('/games/join/', {'code':
                                                       self.game.code.lower(),
                                                       'nickname': 'al'})
            send_message.assert_called_with(self.game.code,
                                            {"type": "player_added",
                                             "player": "al"})

        self.assertEqual(result.status_code, 302)
        self.assertTrue(self.game in self.player.played_games.all())

    def test_join_game_prevents_duplicate_nicknames(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        self.game.players.create(nickname="Existing")
        result = self.client.post('/games/join/', {'code': self.game.code,
                                                   'nickname': 'Existing'})
        self.assertEqual(result.status_code, 302)
        result = self.client.get(result.url)
        self.assertTrue(b"This game already has a player with that nickname"
                        in result.content)

    def test_join_game_when_full(self):
        for i in range(8):
            self.game.players.add(Player.objects.create())

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post('/games/join/', {'code': self.game.code,
                                                   'nickname': 'al'})

        self.assertEqual(result.status_code, 302)
        self.assertFalse(self.game in self.player.played_games.all())
        self.assertTrue("games/play" in result.url)
        self.assertTrue(f"code={self.game.code}" in result.url)

    def test_index_page_allows_player_rejoin_game_in_progress(self):
        self.game.players.add(self.player)
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get('/')
        self.assertTrue(f"Rejoin {self.game.code}?".encode() in result.content)
        self.assertFalse(b"Start a game" in result.content)


class GameRegisteringTestCase(TestCase):
    def setUp(self):
        self.player = Player.objects.create(nickname="joe")
        self.owner = Player.objects.create(nickname="owner")

        self.game = Game.objects.create(code='ABCD',
                                        owner=self.owner)
        self.game.players.add(self.owner)
        self.game.players.add(self.player)

        self.client = Client()

    def test_show_game_as_current_player(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Players" in result.content)
        self.assertTrue(f"{self.player.nickname} (you)".encode()
                        in result.content)
        self.assertFalse(b"If everyone is in" in result.content)

    def test_show_game_as_owner_not_enough_players(self):
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})
        self.game.players.remove(self.player)

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Players" in result.content)
        self.assertTrue(f"{self.owner.nickname}".encode() in result.content)

        self.assertFalse(re.search(b"button.*Start", result.content))
        self.assertTrue(b"We need at least two players to begin.",
                        result.content)

    def test_show_game_as_owner_with_enough_players(self):
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})
        self.game.players.add(self.owner)

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Players" in result.content)
        self.assertTrue(f"{self.player.nickname}".encode() in result.content)

        self.assertTrue(re.search(b"button.*Start", result.content))
        self.assertTrue(b"Everyone in?" in result.content)

    def test_show_game_as_owner_with_max_players(self):
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})

        for i in range(7):
            self.game.players.add(Player.objects.create())

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Players" in result.content)

        self.assertTrue(re.search(b"button.*Start", result.content))
        self.assertTrue(b"Game is full" in
                        result.content)

    def test_show_game_to_unregistered_with_room_left(self):
        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertFalse(b"Players" in result.content)

        self.assertTrue(b"Would you like to join?" in result.content)

    def test_show_game_to_unregistered_with_full_game(self):
        result = self.client.get(f"/games/play/?code={self.game.code}")

        for i in range(7):
            self.game.players.add(Player.objects.create())

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Sorry, this game is already full" in result.content)
        self.assertTrue(b"Would you like to start a new one?"
                        in result.content)

    def test_unknown_code(self):
        result = self.client.get("/games/play/?code=invalid")
        _unknown_code(self, result)

    def test_cancel_game_ignores_non_owner(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.post(f"/games/cancel/{self.game.code}/")
        self.assertEqual(result.status_code, 404)

    def test_cancel_game(self):
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})

        with patch('games.views.send_channel_message') as send_message:
            result = self.client.post(f"/games/cancel/{self.game.code}/")
            send_message.assert_called_with(self.game.code,
                                            {"type": "cancel_game"})

        self.assertEqual(result.status_code, 200)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, GameStatus.ABANDONED)
        self.assertTrue('Cancelled' in self.game.scoring_results['status'])


class GameInProgressTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(GameInProgressTestCase, cls).setUpClass()
        cls.player = Player.objects.create(nickname="player1")

        cls.password = "abc123"
        cls.user = User.objects.create(username="test@test.tld")
        cls.user.set_password(cls.password)
        cls.user.save()
        cls.user_player = Player.objects.create(user=cls.user,
                                                nickname="player2")

        cls.game = Game.objects.create(code='ABCD',
                                       scoring_results={'round_totals': {}},
                                       status=GameStatus.GUESSING_ONE,
                                       owner=cls.user_player)

        cls.game.players.add(cls.player)
        cls.game.players.add(cls.user_player)
        cls.game.players.add(Player.objects.create(nickname="player3"))

        content_file = ContentFile("not a real image",
                                   name="image")
        image = Image.objects.create(caption="This is a guess",
                                     file=content_file)
        cls.rownd = Round.objects.create(game=cls.game, order=1, image=image)

        cls.client = Client()

    @classmethod
    def tearDownClass(cls):
        super(GameInProgressTestCase, cls).tearDownClass()
        img_dir = os.path.join(settings.MEDIA_ROOT, "images")
        for f in os.listdir(img_dir):
            if f.startswith("image"):
                os.remove(os.path.join(img_dir, f))

    def test_show_in_progress_game_to_unregistered(self):
        unregistered = Player.objects.create(nickname="unreg")
        self.client.cookies.load({'player_id': unregistered.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")

        _unknown_code(self, result)

    def test_show_picture_to_active_player(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Round ONE" in result.content)
        self.assertTrue(b"What prompt generated this picture"
                        in result.content)
        self.assertTrue(b"<img" in result.content)
        self.assertTrue(re.search(b"input.*type=\"submit\".*Submit",
                                  result.content))

    def test_player_submits_guess(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        guess_text = "frog lips"
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }

        result = self.client.post("/games/make_guess/", data)

        self.assertTrue(b"Guess submitted" in result.content)

        self.assertTrue(self.player.guesses
                        .filter(rownd=self.rownd,
                                text=guess_text.upper()).count() == 1)

    def test_player_cant_guess_twice(self):
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        guess_text = "frog lips"
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }

        self.rownd.guesses.create(text="existing guess", player=self.player)
        result = self.client.post("/games/make_guess/", data)
        self.assertEqual(result.status_code, 400)
        self.assertTrue(self.player.guesses
                        .filter(rownd=self.rownd).count() == 1)

    def test_non_player_cant_guess(self):
        other_player = Player.objects.create(nickname="other")
        self.client.cookies.load({'player_id': other_player.anonymous_user_id})
        guess_text = "frog lips"
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }

        result = self.client.post("/games/make_guess/", data)
        self.assertEqual(result.status_code, 400)
        self.assertTrue(other_player.guesses.count() == 0)

    def test_players_cant_duplicate_guesses(self):
        guess_text = self.rownd.image.caption.lower()
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }
        self.rownd.guesses.create(text=guess_text.upper())

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post("/games/make_guess/", data)
        self.assertTrue(
            b"Too similar to the real caption or another player's guess"
            in result.content)

    def test_duplicate_check_ignores_spaces(self):
        guess_text = self.rownd.image.caption.lower()
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }
        self.rownd.guesses.create(text=guess_text.replace(" ", "").upper())

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post("/games/make_guess/", data)
        self.assertTrue(
            b"Too similar to the real caption or another player's guess"
            in result.content)

    def test_quote_marks_are_supported(self):
        guess_text = "This guess has a ' mark"
        self.rownd.image.caption = guess_text
        self.rownd.image.save()
        data = {
            "rownd_id": self.rownd.id,
            "guess": guess_text
        }
        self.rownd.guesses.create(text=guess_text.replace(" ", "").upper())

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post("/games/make_guess/", data)
        self.assertTrue(
            b"Too similar to the real caption or another player's guess"
            in result.content)

    def test_show_answered_to_active_player(self):
        self.rownd.guesses.create(player=self.player,
                                  text="HOTDOG")
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Guess submitted" in result.content)

    def test_show_later_round_picture(self):
        self.game.status = GameStatus.GUESSING_THREE
        self.game.save()
        self.rownd.order = 3
        self.rownd.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Round THREE" in result.content)

    def test_show_voting_to_active_player(self):
        self.game.status = GameStatus.VOTING_ONE
        self.game.save()

        for player in self.game.players.all():
            self.rownd.guesses.create(player=player,
                                      text=f"{player.nickname} guess")

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Which is the original?" in result.content)

        self.assertFalse(re.search(f"button.*{self.player.nickname} guess",
                                   result.content.decode('utf-8')))

        for player in self.game.players.exclude(pk=self.player.pk):
            self.assertTrue(re.search(f"button.*{player.nickname} guess",
                                      result.content.decode('utf-8')))

    def test_player_votes(self):
        self.game.status = GameStatus.VOTING_ONE
        self.game.save()

        guess = self.rownd.guesses.create(player=self.user_player,
                                          text="user guess")
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post('/games/vote/', {'guess_id': guess.id})

        self.assertTrue(b"Vote submitted" in result.content)
        self.assertTrue(self.player.vote_set.filter(guess=guess).exists())

    def test_non_player_cant_vote(self):
        self.game.status = GameStatus.VOTING_ONE
        self.game.save()

        guess = self.rownd.guesses.create(player=self.user_player,
                                          text="user guess")
        other_player = Player.objects.create(nickname="other")
        self.client.cookies.load({'player_id': other_player.anonymous_user_id})
        result = self.client.post('/games/vote/', {'guess_id': guess.id})

        self.assertFalse(guess.votes.filter(player=other_player).exists())
        self.assertEqual(result.status_code, 400)

    def test_player_cant_vote_twice(self):
        self.game.status = GameStatus.VOTING_ONE
        self.game.save()

        guess = self.rownd.guesses.create(player=self.user_player,
                                          text="user guess")
        guess.votes.create(player=self.player)
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post('/games/vote/', {'guess_id': guess.id})

        self.assertEqual(result.status_code, 400)
        self.assertFalse(b"Vote submitted" in result.content)
        self.assertEqual(self.player.vote_set.filter(guess=guess).count(), 1)

    def test_show_voted_to_active_player(self):
        self.game.status = GameStatus.VOTING_ONE
        self.game.save()

        guess = self.rownd.guesses.create(player=self.user_player,
                                          text="user guess")
        guess.votes.create(player=self.player)
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"Vote submitted" in result.content)

    def __setup_votes(self):
        self.rownd.order = 3
        self.rownd.save()
        self.rownd.guesses.create(player=None,
                                  text="THIS WAS CORRECT")
        players = list(self.game.players.all())
        for i in range(3):
            guess = self.rownd.guesses.create(player=players[i],
                                              text=f"GUESS {i}")
            for j in range(1 + i):
                guess.votes.create(player=players[(i + 1) % 3])

        compute_score(self.rownd, self.game)

    def test_reveal_step_1(self):
        self.__setup_votes()
        self.game.status = GameStatus.REVEAL_THREE
        self.game.reveal_step = 1
        self.game.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"GUESS 0" in result.content)
        self.assertTrue(b"1 Vote" in result.content)

    def test_reveal_step_2(self):
        self.__setup_votes()
        self.game.status = GameStatus.REVEAL_THREE
        self.game.reveal_step = 2
        self.game.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"GUESS 1" in result.content)
        self.assertTrue(b"2 Votes" in result.content)

    def test_reveal_step_3(self):
        self.__setup_votes()
        self.game.status = GameStatus.REVEAL_THREE
        self.game.reveal_step = 3
        self.game.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"GUESS 2" in result.content)
        self.assertTrue(b"3 Votes" in result.content)

    def test_reveal_step_correct_answer(self):
        self.__setup_votes()
        self.game.status = GameStatus.REVEAL_THREE
        self.game.reveal_step = 4
        self.game.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        self.assertTrue(b"THIS WAS CORRECT" in result.content)
        self.assertTrue(b"0 Votes" in result.content)

    def test_reveal_step_show_scores(self):
        self.__setup_votes()
        self.game.status = GameStatus.REVEAL_THREE
        self.game.reveal_step = 99
        self.game.save()

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})

        result = self.client.get(f"/games/play/?code={self.game.code}")

        players = list(self.game.players.all())
        content = result.content.decode('utf-8')

        self.assertTrue(re.search(f">1<.*\n.*>{players[2].nickname}<.*\n.*>3<",
                                  content))
        self.assertTrue(re.search(f">2<.*\n.*>{players[1].nickname}<.*\n.*>2<",
                                  content))
        self.assertTrue(re.search(f">3<.*\n.*>{players[0].nickname}<.*\n.*>1<",
                                  content))


class GameFinishedTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super(GameFinishedTestCase, cls).setUpClass()
        cls.player = Player.objects.create(nickname="player1")

        cls.password = "abc123"
        cls.owner = Player.objects.create(nickname="player2")

        games = []
        for i in range(3):
            game = Game.objects.create(
                code='ABCD',
                scoring_results={'round_totals': {}},
                status=GameStatus.COMPLETE,
                owner=cls.owner)
            game.players.add(cls.owner)
            game.players.add(cls.player)
            games.append(game)

            content_file = ContentFile("not a real image",
                                       name=f"image{i}")
            image = Image.objects.create(file=content_file,
                                         caption=f"image {i} title")
            rownd = game.rounds.create(order=1, image=image)
            guess = rownd.guesses.create(player=None, text='Real answer')
            guess.votes.create(player=cls.player)

        cls.game = games[-1]

    def test_show_restart_button_to_owner(self):
        context = running_game_context(self.game, self.owner)
        template = loader.get_template('game_content.html')
        html = template.render(context, None)

        self.assertTrue("Play again with the same players?"
                        in html)

    def test_dont_show_restart_button_if_game_is_closed(self):
        self.game.closed = True
        context = running_game_context(self.game, self.owner)
        template = loader.get_template('game_content.html')
        html = template.render(context, None)

        self.assertFalse("Play again with the same players?"
                         in html)
        self.game.closed = False

    def test_dont_show_restart_button_to_non_owner(self):
        context = running_game_context(self.game, self.player)
        template = loader.get_template('game_content.html')
        html = template.render(context, None)

        self.assertFalse("Play again with the same players?"
                         in html)

    def test_new_game_with_same_players(self):
        data = {"code": self.game.code}
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})

        with patch('games.views.send_channel_message') as send_message:
            with patch('games.views.timer_tick') as timer_tick:
                result = self.client.post("/games/reuse_game_code/", data)
                send_message.assert_called_with(self.game.code,
                                                {"type": "new_game"})
                timer_tick.assert_called_once()

        self.assertEqual(result.status_code, 200)
        new_game = (Game.objects
                        .filter(code=self.game.code,
                                status=GameStatus.STARTING)
                        .first())
        self.assertEqual(new_game.owner, self.game.owner)
        self.assertCountEqual(new_game.players.values_list('id'),
                              self.game.players.values_list('id'))

    def test_new_game_only_works_for_owner(self):
        data = {"code": self.game.code}

        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.post("/games/reuse_game_code/", data)

        self.assertEqual(result.status_code, 404)

    def test_close_current_game_code(self):
        data = {"code": self.game.code}
        self.client.cookies.load({'player_id': self.owner.anonymous_user_id})

        with patch('games.views.send_channel_message') as send_message:
            result = self.client.post("/games/close_game_code/", data)
            send_message.assert_called_with(self.game.code,
                                            {"type": "close_game"})

        self.game.refresh_from_db()
        self.assertTrue(self.game.closed)
        self.assertEqual(result.status_code, 200)

    def test_old_game_returns_not_found(self):
        Game.objects.filter(code=self.game.code).update(created=timezone.now() - timezone.timedelta(days=3))
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")
        _unknown_code(self, result)

    def test_recent_game_shows_final_page(self):
        Game.objects.filter(code=self.game.code).update(created=timezone.now())
        self.client.cookies.load({'player_id': self.player.anonymous_user_id})
        result = self.client.get(f"/games/play/?code={self.game.code}")
        self.assertTrue(b"Final Score" in result.content)
        self.assertTrue(b"Best Answers" in result.content)
        self.assertTrue(b"Hardest Prompt" in result.content)
        self.assertTrue(b"Easiest Prompt" in result.content)
