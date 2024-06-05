from django import forms


class GameForm(forms.Form):
    nickname = forms.CharField(label='Nickname', max_length=20)


class JoinForm(forms.Form):
    nickname = forms.CharField(label='Nickname', max_length=20)
    code = forms.CharField(label='Game Code', max_length=5)


class GuessForm(forms.Form):
    rownd_id = forms.IntegerField(label="Round")
    guess = forms.CharField(label="Guess", max_length=50)


class VoteForm(forms.Form):
    guess_id = forms.IntegerField(label="Guess")
