import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.db.models import Q
from django.template import loader

from games.models import Game, GameStatus, Player
from games.utils import running_game_context


class RunningGameConsumer(WebsocketConsumer):
    def connect(self):
        player_id = self.scope['cookies'].get('player_id')
        code = self.scope['url_route']['kwargs'].get('code')

        self.player = Player.objects.get(anonymous_user_id=player_id)
        self.game = (Game.objects
                     .filter(code=code, players=self.player)
                     .exclude(closed=True)
                     .order_by('-created')
                     .first())

        if self.game and self.player:
            async_to_sync(self.channel_layer.group_add)(self.game.code,
                                                        self.channel_name)
            self.accept()

    def disconnect(self, close_code):
        if self.game:
            async_to_sync(self.channel_layer.group_discard)(self.game.code,
                                                            self.channel_name)

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")

        if message.lower() == 'ping':
            self.send(text_data=json.dumps({"message": "pong"}))
        else:
            self.send(text_data=json.dumps({"message": message}))

    def countdown_update(self, event):
        remaining = event.get("remaining", '')
        class_name = "text-red-800" if remaining and int(remaining) <= 5 else ""
        class_name += " min-h-lg"
        html = f'<p id="countdown_time" hx-swap-oob="true" class="{class_name}">{remaining}</p>'
        self.send(text_data=html)

    def refresh_game_content(self, event):
        self.game.refresh_from_db()
        context = running_game_context(self.game, self.player)
        template = loader.get_template('game_content.html')
        html = template.render(context, None)

        html = f'<div id="game_content" hx-swap-oob="true"> { html } </div>'

        self.send(text_data=html)

    def player_added(self, event):
        player = event.get("player", "")

        if player:
            html = ('<div hx-swap-oob="beforeend:#player-list">'
                    f'<li>{player}</li></div>')
            self.send(text_data=html)

        if self.game.owner == self.player:
            count = self.game.players.count()
            context = {
                'enough_players': count > 1,
                'game_full': count >= 8,
                'code': self.game.code,
            }
            template = loader.get_template('owner_start_message.html')
            html = template.render(context, None)
            html = (f'<div id="owner_message" hx-swap-oob="true"> { html } '
                    '</div>')

            self.send(text_data=html)

    def new_game(self, event):
        self.game = (Game.objects
                     .exclude(Q(status=GameStatus.COMPLETE) |
                              Q(status=GameStatus.ABANDONED))
                     .filter(code=self.game.code)
                     .first())

    def close_game(self, event):
        template = loader.get_template('game_closed.html')
        html = template.render({}, None)

        html = f'<div id="finished_game_message" hx-swap-oob="true"> { html } </div>'
        self.send(text_data=html)

        self.disconnect(None)

    def cancel_game(self, event):
        template = loader.get_template('game_closed.html')
        html = template.render({'cancelled': True}, None)

        html = f'<div id="game_content" hx-swap-oob="true"> { html } </div>'
        self.send(text_data=html)

        self.disconnect(None)
