"""
Обработчик плейлистов
"""

import re
import asyncio
from typing import Dict, List, Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import (
    MESSAGES,
    KEYBOARDS,
    ConversationState,
    MAX_PLAYLIST_SIZE,
    REQUEST_TIMEOUT
)
from bot.utils.error_handler import handle_errors, with_timeout
from bot.services.spotify_service import SpotifyService
from bot.services.yandex_service import YandexMusicService
from bot.services.analysis_service import AnalysisService
from bot.services.cache_service import CacheService

class PlaylistHandler:
    """Обработчик плейлистов"""
    
    def __init__(self):
        self.spotify_service = SpotifyService()
        self.yandex_service = YandexMusicService()
        self.analysis_service = AnalysisService()
        self.cache_service = CacheService()
        self.bot = None
    
    def set_bot(self, bot):
        """Установка ссылки на основного бота"""
        self.bot = bot
    
    @handle_errors
    async def request_playlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрос ссылки на плейлист"""
        await update.message.reply_text(
            MESSAGES['playlist_prompt'],
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True)
        )
        
        return ConversationState.ENTER_PLAYLIST.value
    
    @handle_errors
    @with_timeout(PLAYLIST_FETCH_TIMEOUT)
    async def receive_playlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Получение и обработка плейлиста"""
        text = update.message.text.strip()
        
        # Проверка на отмену
        if text.lower() == 'отмена':
            await self.bot.cancel(update, context)
            return ConversationState.SELECTING_ACTION.value
        
        # Валидация ссылки
        if not self.validate_playlist_url(text):
            await update.message.reply_text(MESSAGES['error_invalid_url'])
            return ConversationState.ENTER_PLAYLIST.value
        
        # Показываем статус обработки
        status_msg = await update.message.reply_text("Анализирую плейлист...")
        
        try:
            # Определяем сервис и получаем треки
            service = self.identify_service(text)
            tracks = await self.fetch_playlist_tracks(text, service)
            
            if not tracks:
                await status_msg.edit_text(MESSAGES['error_no_tracks'])
                return ConversationState.ENTER_PLAYLIST.value
            
            if len(tracks) > MAX_PLAYLIST_SIZE:
                await status_msg.edit_text(
                    MESSAGES['error_playlist_too_big'].format(max=MAX_PLAYLIST_SIZE)
                )
                return ConversationState.ENTER_PLAYLIST.value
            
            # Анализируем плейлист
            analysis = await self.analyze_playlist(tracks)
            
            # Сохраняем анализ в профиль пользователя
            user_id = update.effective_user.id
            await self.bot.profile_handler.save_playlist_analysis(user_id, analysis)
            
            # Отправляем результаты
            await self.send_analysis_results(update, analysis, len(tracks))
            
            # Награждаем достижением
            await self.bot.profile_handler.award_achievement(user_id, 'first_analysis')
            
            # Очищаем состояние контекста
            if context.user_data:
                context.user_data.clear()
            
            return ConversationState.VIEWING_ANALYSIS.value
            
        except asyncio.TimeoutError:
            await status_msg.edit_text(MESSAGES['error_timeout'])
            return ConversationState.SELECTING_ACTION.value
        except Exception as e:
            await status_msg.edit_text(f"Ошибка: {str(e)}")
            return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    async def analyze_playlist_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /analyze"""
        args = context.args
        
        if args:
            # Анализ по ссылке из аргументов
            text = ' '.join(args)
            update.message.text = text
            return await self.receive_playlist(update, context)
        else:
            # Запрос ссылки
            return await self.request_playlist(update, context)
    
    def validate_playlist_url(self, url: str) -> bool:
        """Валидация URL плейлиста"""
        patterns = [
            r'https?://open\.spotify\.com/playlist/[a-zA-Z0-9]+',
            r'https?://music\.yandex\.ru/users/[^/]+/playlists/\d+',
            r'https?://music\.yandex\.ru/album/\d+/tracks',
            r'https?://music\.apple\.com/.*/playlist/.*'
        ]
        
        return any(re.match(pattern, url) for pattern in patterns)
    
    def identify_service(self, url: str) -> str:
        """Определение музыкального сервиса по URL"""
        if 'spotify' in url:
            return 'spotify'
        elif 'yandex' in url:
            return 'yandex'
        elif 'apple' in url:
            return 'apple'
        else:
            return 'unknown'
    
    async def fetch_playlist_tracks(self, url: str, service: str) -> List[Dict]:
        """Получение треков из плейлиста"""
        # Проверяем кэш
        cache_key = f"playlist_{hash(url)}"
        cached = await self.cache_service.get(cache_key)
        
        if cached:
            return cached
        
        # Получаем треки из сервиса
        if service == 'spotify':
            tracks = await self.spotify_service.get_playlist_tracks(url)
        elif service == 'yandex':
            tracks = await self.yandex_service.get_playlist_tracks(url)
        else:
            # Для других сервисов или прямого ввода
            tracks = await self.parse_tracks_from_text(url)
        
        # Сохраняем в кэш
        if tracks:
            await self.cache_service.set(cache_key, tracks, ttl=3600)
        
        return tracks
    
    async def parse_tracks_from_text(self, text: str) -> List[Dict]:
        """Парсинг треков из текста (если не ссылка)"""
        # Пример: "Artist - Song, Artist2 - Song2"
        tracks = []
        lines = text.split(',')
        
        for line in lines:
            if '-' in line:
                parts = line.split('-', 1)
                if len(parts) == 2:
                    tracks.append({
                        'artist': parts[0].strip(),
                        'title': parts[1].strip(),
                        'service': 'manual'
                    })
        
        return tracks
    
    async def analyze_playlist(self, tracks: List[Dict]) -> Dict:
        """Анализ плейлиста"""
        return await self.analysis_service.analyze_tracks(tracks)
    
    async def send_analysis_results(self, update: Update, analysis: Dict, track_count: int):
        """Отправка результатов анализа"""
        # Форматируем текст
        genres_text = ""
        for i, (genre, percentage) in enumerate(analysis.get('top_genres', []), 1):
            genres_text += f"{i}. {genre}: {percentage:.1%}\n"
        
        analysis_text = MESSAGES['analysis_complete'].format(
            mood=analysis.get('mood', 'Не определено'),
            energy=analysis.get('energy_score', 0),
            danceability=analysis.get('danceability_score', 0),
            popularity=analysis.get('popularity_score', 0),
            genres=genres_text,
            top_artist=analysis.get('top_artist', 'Не определен'),
            top_track=analysis.get('top_track', 'Не определен')
        )
        
        # Создаем клавиатуру для дополнительных действий
        keyboard = [
            ["Подробная статистика"],
            ["Получить рекомендации"],
            ["Сравнить с друзьями"],
            ["Главное меню"]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        # Добавляем информацию о количестве треков
        header = f"Проанализировано {track_count} треков\n\n"
        
        await update.message.reply_text(
            header + analysis_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Отправляем дополнительную информацию если есть
        if analysis.get('interesting_facts'):
            facts_text = "*Интересные факты:*\n\n"
            for fact in analysis['interesting_facts'][:3]:  # Ограничиваем 3 фактами
                facts_text += f"• {fact}\n"
            
            await update.message.reply_text(facts_text, parse_mode='Markdown')
