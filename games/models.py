import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Player(models.Model):
    nickname = models.CharField(default="", max_length=20)
    anonymous_user_id = models.UUIDField(default=uuid.uuid4)
    user = models.ForeignKey(on_delete=models.SET_NULL,
                             null=True, blank=True, to='auth.User')
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.id}: {self.nickname}"


class GameStatus(models.TextChoices):
    STARTING = 'ST', _('Starting')
    GUESSING_ONE = 'R1', _('Guessing Round One')
    GUESSING_TWO = 'R2', _('Guessing Round Two')
    GUESSING_THREE = 'R3', _('Guessing Round Three')
    GUESSING_FOUR = 'R4', _('Guessing Round Four')
    GUESSING_FIVE = 'R5', _('Guessing Round Five')
    VOTING_ONE = 'V1', _('Voting Round One')
    VOTING_TWO = 'V2', _('Voting Round Two')
    VOTING_THREE = 'V3', _('Voting Round Three')
    VOTING_FOUR = 'V4', _('Voting Round Four')
    VOTING_FIVE = 'V5', _('Voting Round Five')
    REVEAL_ONE = 'S1', _('Show Score Round One')
    REVEAL_TWO = 'S2', _('Show Score Round Two')
    REVEAL_THREE = 'S3', _('Show Score Round Three')
    REVEAL_FOUR = 'S4', _('Show Score Round Four')
    REVEAL_FIVE = 'S5', _('Show Score Round Five')
    COMPLETE = 'CM', _('Complete')
    ABANDONED = 'AB', _('Abandoned')


class Game(models.Model):

    code = models.CharField(max_length=5)
    status = models.CharField(max_length=2, choices=GameStatus.choices,
                              default=GameStatus.STARTING)
    owner = models.ForeignKey(to='games.Player', on_delete=models.CASCADE,
                              related_name='owned_games')
    players = models.ManyToManyField(to='games.Player',
                                     related_name='played_games')
    created = models.DateTimeField(auto_now_add=True)
    next_update = models.DateTimeField(null=True, blank=True)
    reveal_step = models.IntegerField(default=1)
    scoring_results = models.JSONField(blank=True, null=True, default=dict)
    closed = models.BooleanField(default=False)

    def __str__(self):
        return self.code


class Round(models.Model):
    game = models.ForeignKey(to='games.Game', on_delete=models.CASCADE,
                             related_name='rounds')
    order = models.IntegerField(default=1)
    image = models.ForeignKey(to='images.Image', on_delete=models.CASCADE)


class Guess(models.Model):
    rownd = models.ForeignKey(to='games.Round', on_delete=models.CASCADE,
                              related_name='guesses')
    player = models.ForeignKey(to='games.Player', on_delete=models.CASCADE,
                               null=True, related_name='guesses')
    text = models.CharField(default="", max_length=50)


class Vote(models.Model):
    player = models.ForeignKey(to='games.Player', on_delete=models.CASCADE,)
    guess = models.ForeignKey(to='games.Guess', on_delete=models.CASCADE,
                              related_name='votes')
