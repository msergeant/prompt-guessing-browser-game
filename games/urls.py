from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('games/create/', views.game_create, name='game_create'),
    path('games/play/', views.show_game, name='show_game'),
    path('games/join/', views.join_game, name='join_game'),
    path('games/make_guess/', views.submit_guess, name='submit_guess'),
    path('games/vote/', views.submit_vote, name='submit_vote'),
    path('games/start/<str:code>/', views.start_game_clock,
         name='start_game_clock'),
    path('games/reuse_game_code/', views.reuse_game_code,
         name='reuse_game_code'),
    path('games/close_game_code/', views.close_game_code,
         name='close_game_code'),
    path('games/cancel/<str:code>/', views.cancel_game_code,
         name='cancel_game_code'),
    path('game-summary/<int:pk>/', views.summary,
         name='game_summary'),
]

if settings.ENVIRONMENT == 'dev':
    urlpatterns += [path('games/dev_pages/', views.dev_pages, name='dev_only')]
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL,
                          document_root=settings.STATIC_ROOT)
