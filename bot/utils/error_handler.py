"""
Утилиты для обработки ошибок и таймаутов
"""

import asyncio
import functools
import logging
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes, Application

from config import MESSAGES, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

def handle_errors(func: Callable) -> Callable:
    """
    Декоратор для обработки ошибок в хендлерах
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут в функции {func.__name__}")
            update = next((arg for arg in args if isinstance(arg, Update)), None)
            if update and hasattr(update, 'message'):
                await update.message.reply_text(MESSAGES['error_timeout'])
            return None
        except Exception as e:
            logger.error(f"Ошибка в функции {func.__name__}: {e}", exc_info=True)
            update = next((arg for arg in args if isinstance(arg, Update)), None)
            if update and hasattr(update, 'message'):
                await update.message.reply_text(
                    f"Произошла ошибка: {str(e)[:100]}"
                )
            return None
    return wrapper

def with_timeout(timeout: int = REQUEST_TIMEOUT):
    """
    Декоратор для установки таймаута на выполнение функции
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Таймаут {timeout}с в функции {func.__name__}")
                raise
        return wrapper
    return decorator

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Глобальный обработчик ошибок
    """
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Определяем тип ошибки
    error = context.error
    
    if isinstance(error, asyncio.TimeoutError):
        error_message = MESSAGES['error_timeout']
    elif isinstance(error, ConnectionError):
        error_message = MESSAGES['error_service_unavailable']
    else:
        error_message = f"Непредвиденная ошибка: {str(error)[:150]}"
    
    # Отправляем сообщение об ошибке если есть куда
    if update and isinstance(update, Update):
        if update.message:
            await update.message.reply_text(error_message)
        elif update.callback_query:
            await update.callback_query.message.reply_text(error_message)
    
    # Очищаем состояние пользователя при критических ошибках
    if hasattr(context, 'user_data') and context.user_data:
        context.user_data.clear()

def setup_error_handlers(application: Application):
    """
    Настройка обработчиков ошибок для приложения
    """
    application.add_error_handler(error_handler)
    
    # Можно добавить дополнительные обработчики для конкретных типов ошибок
    # application.add_error_handler(handle_timeout, asyncio.TimeoutError)
    # application.add_error_handler(handle_network_error, (ConnectionError, TimeoutError))

async def handle_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка таймаутов"""
    logger.warning("Таймаут при обработке запроса")
    
    if update.message:
        await update.message.reply_text(
            MESSAGES['error_timeout'],
            reply_markup=None  # Убираем клавиатуру при ошибке
        )
    
    # Очищаем состояние
    if context.user_data:
        context.user_data.clear()

class StateManager:
    """
    Менеджер состояний для очистки и управления
    """
    
    @staticmethod
    def clear_user_state(context: ContextTypes.DEFAULT_TYPE):
        """Очистка состояния пользователя"""
        if hasattr(context, 'user_data') and context.user_data:
            context.user_data.clear()
            logger.info("Состояние пользователя очищено")
    
    @staticmethod
    def save_state(context: ContextTypes.DEFAULT_TYPE, key: str, value: Any):
        """Сохранение состояния"""
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        
        context.user_data[key] = value
    
    @staticmethod
    def load_state(context: ContextTypes.DEFAULT_TYPE, key: str, default: Any = None) -> Any:
        """Загрузка состояния"""
        if hasattr(context, 'user_data'):
            return context.user_data.get(key, default)
        return default
