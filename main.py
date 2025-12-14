"""
Главный файл запуска бота
"""

import os
import sys
import logging
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import (
    TELEGRAM_TOKEN, 
    ConversationState,
    MESSAGES,
    LOGS_DIR
)
from bot.music_taste_bot import MusicTasteBot
from bot.handlers.playlist_handler import PlaylistHandler
from bot.handlers.profile_handler import ProfileHandler
from bot.handlers.recommendation_handler import RecommendationHandler
from bot.handlers.battle_handler import BattleHandler
from bot.utils.error_handler import setup_error_handlers, handle_timeout

def setup_logging():
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    log_file = os.path.join(
        LOGS_DIR, 
        f"bot_{datetime.now().strftime('%Y%m%d')}.log"
    )
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)

def get_bot_token():
    """
    Получает токен бота из различных источников
    """
    token = TELEGRAM_TOKEN
    
    if token:
        logger.info(f"Токен загружен из переменных окружения ({token[:10]}...)")
        return token
    
    print("=" * 60)
    print("🎵 MUSIC TASTE BOT - Анализатор музыкальных вкусов")
    print("=" * 60)
    print("Для работы бота необходим токен Telegram бота.")
    print("Получить токен можно у @BotFather в Telegram.")
    print("=" * 60)
    
    while True:
        token = input("Введите токен вашего бота: ").strip()
        
        if not token:
            print("❌ Токен не может быть пустым!")
            continue
            
        if ':' not in token:
            print("❌ Неверный формат токена.")
            print("💡 Пример: 8506557163:AAE10B6PML_FHKu2AAEpCQgASXsZnTpbTeDs")
            continue
            
        print(f"✅ Токен принят (длина: {len(token)} символов)")
        print("💡 Совет: Создайте файл .env с TELEGRAM_BOT_TOKEN=ваш_токен")
        print("=" * 60)
        return token

def create_application(token: str):
    """
    Создает и настраивает приложение Telegram бота
    """
    playlist_handler = PlaylistHandler()
    profile_handler = ProfileHandler()
    recommendation_handler = RecommendationHandler()
    battle_handler = BattleHandler()
    
    bot = MusicTasteBot(
        playlist_handler=playlist_handler,
        profile_handler=profile_handler,
        recommendation_handler=recommendation_handler,
        battle_handler=battle_handler
    )
    
    application = Application.builder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            ConversationState.SELECTING_ACTION.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message)
            ],
            ConversationState.ENTER_PLAYLIST.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, playlist_handler.receive_playlist)
            ],
            ConversationState.VIEWING_ANALYSIS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message)
            ],
            ConversationState.WAITING_BATTLE_RESPONSE.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, battle_handler.handle_battle_response)
            ],
            ConversationState.SELECTING_BATTLE_TRACKS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, battle_handler.select_battle_tracks)
            ],
            ConversationState.VIEWING_PROFILE.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_handler.handle_profile_navigation)
            ],
            ConversationState.VIEWING_RECOMMENDATIONS.value: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recommendation_handler.handle_recommendations)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', bot.cancel),
            CommandHandler('start', bot.start)
        ],
        allow_reentry=True,
        conversation_timeout=300  # 5 минут таймаут для неактивных конверсаций
    )
    
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("profile", profile_handler.show_profile))
    application.add_handler(CommandHandler("recommend", recommendation_handler.get_recommendations))
    application.add_handler(CommandHandler("analyze", playlist_handler.analyze_playlist_command))
    application.add_handler(CommandHandler("battle", battle_handler.start_battle_command))
    application.add_handler(CommandHandler("stats", profile_handler.show_detailed_stats))
    application.add_handler(CommandHandler("achievements", profile_handler.show_achievements))
    
    application.add_handler(conv_handler)
    
    setup_error_handlers(application)
    
    return application, bot

async def post_init(application):
    logger.info("Бот успешно инициализирован")
    
    bot_info = await application.bot.get_me()
    logger.info(f"Бот @{bot_info.username} готов к работе!")
    
    print(f"\n✅ Бот @{bot_info.username} запущен!")
    print("📊 Статус: Ожидание сообщений...")
    print("💡 Используйте /help для списка команд")
    print("=" * 60)

async def post_stop(application):
    """Действия при остановке бота"""
    logger.info("Остановка бота...")
    logger.info("Бот остановлен")

def main():
    """Основная функция запуска"""
    global logger
    logger = setup_logging()
    
    try:
        logger.info("Запуск Music Taste Bot...")
        
        token = get_bot_token()
        if not token:
            logger.error("Токен не получен. Завершение работы.")
            return
        
        application, bot = create_application(token)
        
        application.post_init = post_init
        application.post_stop = post_stop
        
        logger.info("Запуск polling...")
        application.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True,
            timeout=20,
            read_timeout=20,
            write_timeout=20,
            connect_timeout=20,
            pool_timeout=20
        )
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
        print("\n🛑 Бот остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
