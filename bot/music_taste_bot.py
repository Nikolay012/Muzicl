"""
Основной класс бота - координирует работу всех обработчиков
"""

import asyncio
from typing import Dict, Any, Optional
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from config import (
    MESSAGES, 
    KEYBOARDS, 
    ConversationState,
    BOT_NAME,
    BOT_VERSION
)
from bot.utils.error_handler import handle_errors, with_timeout

class MusicTasteBot:
    """Основной класс бота - фасад для всех обработчиков"""
    
    def __init__(
        self,
        playlist_handler,
        profile_handler,
        recommendation_handler,
        battle_handler
    ):
        self.playlist_handler = playlist_handler
        self.profile_handler = profile_handler
        self.recommendation_handler = recommendation_handler
        self.battle_handler = battle_handler
        
        # Устанавливаем обратные ссылки
        self.playlist_handler.set_bot(self)
        self.profile_handler.set_bot(self)
        self.recommendation_handler.set_bot(self)
        self.battle_handler.set_bot(self)
    
    @handle_errors
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработчик команды /start"""
        welcome_text = MESSAGES['welcome'].format(bot_name=BOT_NAME)
        
        keyboard = KEYBOARDS['main']
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        user_id = update.effective_user.id
        await self.profile_handler.initialize_user(user_id)
        
        return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    @with_timeout(10)
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка текстовых сообщений"""
        text = update.message.text.strip().lower()
        user_id = update.effective_user.id
        
        await self.profile_handler.update_user_activity(user_id)
        
        if text == "проанализировать плейлист":
            return await self.playlist_handler.request_playlist(update, context)
            
        elif text == "мой музыкальный профиль":
            return await self.profile_handler.show_profile_menu(update, context)
            
        elif text == "получить рекомендации":
            return await self.recommendation_handler.request_recommendations(update, context)
            
        elif text == "музыкальные битвы":
            return await self.battle_handler.show_battle_menu(update, context)
            
        elif text == "детальная статистика":
            return await self.profile_handler.show_detailed_stats(update, context)
            
        elif text == "помощь":
            return await self.help_command(update, context)
            
        elif text == "главное меню":
            return await self.show_main_menu(update, context)
            
        else:
            if any(service in text for service in ['http', 'spotify', 'music.yandex', 'apple']):
                return await self.playlist_handler.receive_playlist(update, context)
            else:
                await update.message.reply_text(
                    "Я не понял команду. Используй кнопки меню или /help для справки."
                )
                return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработчик команды /help"""
        help_text = MESSAGES['help']
        
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена текущего действия"""
        await update.message.reply_text(
            "Действие отменено. Возвращаюсь в главное меню.",
            reply_markup=ReplyKeyboardMarkup(KEYBOARDS['main'], resize_keyboard=True)
        )
        
        if context.user_data:
            context.user_data.clear()
        
        return ConversationState.SELECTING_ACTION.value
    
    @handle_errors
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Показ главного меню"""
        keyboard = KEYBOARDS['main']
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Выбери действие:",
            reply_markup=reply_markup
        )
        
        return ConversationState.SELECTING_ACTION.value
    
    def get_user_state(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение состояния пользователя"""
        if not hasattr(self, '_user_states'):
            self._user_states = {}
        
        return self._user_states.get(user_id)
    
    def set_user_state(self, user_id: int, state_data: Dict[str, Any]):
        """Установка состояния пользователя"""
        if not hasattr(self, '_user_states'):
            self._user_states = {}
        
        self._user_states[user_id] = state_data
    
    def clear_user_state(self, user_id: int):
        """Очистка состояния пользователя"""
        if hasattr(self, '_user_states') and user_id in self._user_states:
            del self._user_states[user_id]
