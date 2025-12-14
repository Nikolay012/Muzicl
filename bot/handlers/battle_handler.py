"""
Обработчик музыкальных битв - новая крутая фича!
"""

import random
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from config import (
    MESSAGES,
    KEYBOARDS,
    ConversationState,
    BATTLE_TITLES,
    ACHIEVEMENTS,
    ANALYSIS_PARAMS
)
from bot.utils.error_handler import handle_errors, with_timeout
from bot.services.analysis_service import AnalysisService
from bot.services.cache_service import CacheService

class BattleHandler:
    """Обработчик музыкальных битв"""
    
    def __init__(self):
        self.analysis_service = AnalysisService()
        self.cache_service = CacheService()
        self.active_battles: Dict[str, Dict] = {}
        self.bot = None
    
    def set_bot(self, bot):
        """Установка ссылки на основного бота"""
        self.bot = bot
    
    @handle_errors
    async def start_battle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /battle"""
        args = context.args
        
        if args:
            # Битва с конкретным пользователем
            username = args[0].lstrip('@')
            await self.challenge_user(update, context, username)
        else:
            # Показ меню битв
            await self.show_battle_menu(update, context)
    
    @handle_errors
    async def show_battle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показать меню музыкальных битв"""
        keyboard = KEYBOARDS['battle']
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "⚔️ *Музыкальные битвы*\n\n"
            "Сравни свои музыкальные вкусы с друзьями!\n\n"
            "Выбери действие:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    @with_timeout(30)
    async def challenge_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username: str):
        """Вызвать пользователя на битву"""
        challenger = update.effective_user
        battle_id = f"{challenger.id}_{int(datetime.now().timestamp())}"
        
        self.active_battles[battle_id] = {
            'challenger_id': challenger.id,
            'challenger_name': challenger.full_name,
            'opponent_username': username,
            'status': 'waiting',
            'created_at': datetime.now().isoformat()
        }
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Принять вызов", callback_data=f"accept_{battle_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{battle_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        battle_text = MESSAGES['battle_invite'].format(
            user1=challenger.full_name,
            user2=f"@{username}"
        )
        
        await update.message.reply_text(
            battle_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        context.user_data['pending_battle'] = battle_id
        
        return ConversationState.WAITING_BATTLE_RESPONSE.value
    
    @handle_errors
    async def handle_battle_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ответа на вызов"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if 'pending_battle' not in context.user_data:
            return ConversationState.SELECTING_ACTION.value
        
        battle_id = context.user_data['pending_battle']
        
        if battle_id not in self.active_battles:
            await update.message.reply_text(MESSAGES['error_battle_declined'])
            return ConversationState.SELECTING_ACTION.value
        
        if text.lower() == 'да' or text == '✅':
            await self.start_battle(update, context, battle_id)
        else:
            await update.message.reply_text(MESSAGES['error_battle_declined'])
            self.active_battles[battle_id]['status'] = 'declined'
            
        if 'pending_battle' in context.user_data:
            del context.user_data['pending_battle']
        
        return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    @with_timeout(60)
    async def start_battle(self, update: Update, context: ContextTypes.DEFAULT_TYPE, battle_id: str):
        """Начать музыкальную битву"""
        battle = self.active_battles[battle_id]
        user1_id = battle['challenger_id']
        user2_id = update.effective_user.id
        
        user1_profile = await self.bot.profile_handler.get_user_profile(user1_id)
        user2_profile = await self.bot.profile_handler.get_user_profile(user2_id)
        
        if not user1_profile or not user2_profile:
            await update.message.reply_text("Нужно сначала проанализировать хотя бы один плейлист!")
            return ConversationState.SELECTING_ACTION.value
        
        await update.message.reply_text(
            "Выбери 3 своих лучших трека для битвы (отправь названия через запятую):",
            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True)
        )
        
        context.user_data['battle_data'] = {
            'battle_id': battle_id,
            'user1_id': user1_id,
            'user2_id': user2_id,
            'user1_tracks': [],
            'user2_tracks': [],
            'current_user': user2_id,
            'stage': 'selecting_tracks'
        }
        
        return ConversationState.SELECTING_BATTLE_TRACKS.value
    
    @handle_errors
    async def select_battle_tracks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор треков для битвы"""
        if 'battle_data' not in context.user_data:
            return ConversationState.SELECTING_ACTION.value
        
        battle_data = context.user_data['battle_data']
        text = update.message.text
        
        if text == "Отмена":
            await update.message.reply_text("Битва отменена.")
            return await self.bot.show_main_menu(update, context)
        
        tracks = [t.strip() for t in text.split(',')]
        
        if battle_data['current_user'] == update.effective_user.id:
            if len(tracks) != 3:
                await update.message.reply_text("Нужно выбрать ровно 3 трека!")
                return ConversationState.SELECTING_BATTLE_TRACKS.value
            
            battle_data['user2_tracks'] = tracks
            
            await update.message.reply_text(
                "Отлично! Теперь ждем выбор соперника..."
            )
            
        return ConversationState.SELECTING_BATTLE_TRACKS.value
    
    @handle_errors
    @with_timeout(45)
    async def compare_tracks(self, user1_tracks: List[str], user2_tracks: List[str]) -> Dict:
        """Сравнить треки двух пользователей"""
        # Анализируем треки
        user1_analysis = await self.analyze_tracks_for_battle(user1_tracks)
        user2_analysis = await self.analyze_tracks_for_battle(user2_tracks)
        
        scores = {
            'energy': self.compare_parameter(user1_analysis['energy'], user2_analysis['energy']),
            'danceability': self.compare_parameter(user1_analysis['danceability'], user2_analysis['danceability']),
            'popularity': self.compare_parameter(user1_analysis['popularity'], user2_analysis['popularity']),
            'variety': self.compare_parameter(user1_analysis['genre_variety'], user2_analysis['genre_variety']),
            'exclusivity': self.compare_parameter(user1_analysis['exclusivity'], user2_analysis['exclusivity'])
        }
        user1_score = sum(1 for param, winner in scores.items() if winner == 'user1')
        user2_score = sum(1 for param, winner in scores.items() if winner == 'user2')
        
        title = self.determine_title(scores)
        
        return {
            'user1_score': user1_score,
            'user2_score': user2_score,
            'winner': 'user1' if user1_score > user2_score else 'user2',
            'title': title,
            'detailed_scores': scores,
            'user1_analysis': user1_analysis,
            'user2_analysis': user2_analysis
        }
    
    async def analyze_tracks_for_battle(self, tracks: List[str]) -> Dict:
        """Анализ треков для битвы"""
        return {
            'energy': random.uniform(0.5, 1.0),
            'danceability': random.uniform(0.3, 0.9),
            'popularity': random.uniform(0.4, 1.0),
            'genre_variety': random.uniform(0.2, 0.8),
            'exclusivity': random.uniform(0.1, 0.7),
            'mood': random.choice(['energetic', 'happy', 'calm', 'romantic']),
            'top_genre': random.choice(['pop', 'rock', 'hiphop', 'electronic'])
        }
    
    def compare_parameter(self, value1: float, value2: float) -> str:
        """Сравнение параметра"""
        if abs(value1 - value2) < 0.1:
            return 'draw'
        return 'user1' if value1 > value2 else 'user2'
    
    def determine_title(self, scores: Dict) -> str:
        """Определение титула по результатам битвы"""
        user1_wins = [param for param, winner in scores.items() if winner == 'user1']
        
        if 'energy' in user1_wins and 'danceability' in user1_wins:
            return BATTLE_TITLES['dance_master']
        elif 'popularity' in user1_wins:
            return BATTLE_TITLES['hitmaker']
        elif 'exclusivity' in user1_wins:
            return BATTLE_TITLES['underground_hero']
        else:
            return BATTLE_TITLES['taste_guru']
    
    @handle_errors
    async def show_battle_results(self, update: Update, context: ContextTypes.DEFAULT_TYPE, results: Dict):
        """Показать результаты битвы"""
        battle_data = context.user_data.get('battle_data', {})
        
        results_text = MESSAGES['battle_results'].format(
            winner=battle_data.get('user1_name', 'Игрок 1') if results['winner'] == 'user1' 
                   else battle_data.get('user2_name', 'Игрок 2'),
            score1=results['user1_score'],
            score2=results['user2_score'],
            energy1=f"{results['user1_analysis']['energy']:.1%}",
            energy2=f"{results['user2_analysis']['energy']:.1%}",
            dance1=f"{results['user1_analysis']['danceability']:.1%}",
            dance2=f"{results['user2_analysis']['danceability']:.1%}",
            pop1=f"{results['user1_analysis']['popularity']:.0%}",
            pop2=f"{results['user2_analysis']['popularity']:.0%}",
            var1=f"{results['user1_analysis']['genre_variety']:.1%}",
            var2=f"{results['user2_analysis']['genre_variety']:.1%}",
            excl1=f"{results['user1_analysis']['exclusivity']:.1%}",
            excl2=f"{results['user2_analysis']['exclusivity']:.1%}",
            title=results['title']
        )
        
        visualization = self.create_battle_visualization(results)
        
        await update.message.reply_text(
            results_text + "\n\n" + visualization,
            parse_mode='Markdown'
        )
        
        winner_id = (battle_data['user1_id'] if results['winner'] == 'user1' 
                    else battle_data['user2_id'])
        await self.bot.profile_handler.award_achievement(winner_id, 'battle_champion')
    
    def create_battle_visualization(self, results: Dict) -> str:
        """Создать визуализацию результатов битвы"""
        bars = []
        params = ['Энергия', 'Танцевальность', 'Популярность', 'Разнообразие', 'Эксклюзивность']
        
        for i, (param, winner) in enumerate(results['detailed_scores'].items()):
            if winner == 'user1':
                bar = f"{params[i]}: 🔵 {'█' * 10}🟡 {'░' * 5}"
            elif winner == 'user2':
                bar = f"{params[i]}: 🔵 {'░' * 5}🟡 {'█' * 10}"
            else:
                bar = f"{params[i]}: 🔵 {'█' * 7}🟡 {'█' * 7}"
            bars.append(bar)
        
        return "\n".join(bars)
    
    @handle_errors
    async def show_battle_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю битв пользователя"""
        user_id = update.effective_user.id
        
        history = [
            {"opponent": "Друг 1", "result": "победа", "date": "2024-01-15"},
            {"opponent": "Друг 2", "result": "поражение", "date": "2024-01-10"},
            {"opponent": "Друг 3", "result": "победа", "date": "2024-01-05"},
        ]
        
        history_text = "📜 *История битв:*\n\n"
        for battle in history:
            result_emoji = "✅" if battle['result'] == 'победа' else "❌"
            history_text += f"{result_emoji} {battle['date']} - {battle['opponent']}\n"
        
        await update.message.reply_text(history_text, parse_mode='Markdown')
    
    @handle_errors
    async def show_battle_leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать рейтинг игроков"""
        # В реальной реализации - загрузка из БД
        leaderboard = [
            {"name": "Алексей", "wins": 15, "rating": 1850},
            {"name": "Мария", "wins": 12, "rating": 1760},
            {"name": "Иван", "wins": 10, "rating": 1680},
            {"name": "Елена", "wins": 8, "rating": 1590},
            {"name": update.effective_user.first_name, "wins": 5, "rating": 1450, "current": True}
        ]
        
        leaderboard_text = "*Рейтинг игроков:*\n\n"
        
        for i, player in enumerate(leaderboard, 1):
            prefix = "➡️" if player.get('current') else f"{i}."
            leaderboard_text += f"{prefix} {player['name']} - {player['wins']} побед (рейтинг: {player['rating']})\n"
        
        await update.message.reply_text(leaderboard_text, parse_mode='Markdown')
