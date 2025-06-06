"""
Главный файл бота клуба X10.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, LabeledPrice, PreCheckoutQuery

# Импортируем конфигурацию и базу данных
from config import load_config
from database import Database
from scheduled_tasks import ScheduledTasks

# Импортируем обработчики
from handlers import start, referral, club, events, admin

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# Команды бота
async def set_commands(bot: Bot):
    """
    Установка команд бота
    """
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="menu", description="Главное меню"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(commands)


# Обработчики предварительных проверок платежей
async def register_payment_handlers(dp: Dispatcher):
    """
    Регистрация обработчиков платежей
    """
    @dp.pre_checkout_query()
    async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
        """Обработчик предварительной проверки платежей"""
        # Здесь мы всегда принимаем платеж (в реальном приложении могут быть проверки)
        await pre_checkout_query.answer(ok=True)


# Инициализация бота
async def main():
    """
    Главная функция запуска бота
    """
    # Загрузка конфигурации
    config = load_config()

    # Инициализация бота и диспетчера
    bot = Bot(token=config.bot.token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Инициализация базы данных
    db = Database(config.db.db_path)
    await db.create_tables()

    # Регистрация middlewares
    # ПРИМЕЧАНИЕ: Здесь будет добавлен middleware для передачи конфигурации и БД
    dp.message.middleware.register(ConfigMiddleware(config, db, bot))
    dp.callback_query.middleware.register(ConfigMiddleware(config, db, bot))

    # Регистрация обработчиков
    dp.include_router(start.router)
    dp.include_router(referral.router)
    dp.include_router(club.router)
    dp.include_router(events.router)
    dp.include_router(admin.router)

    # Регистрация обработчиков платежей
    await register_payment_handlers(dp)

    # Установка команд бота
    await set_commands(bot)

    # Инициализация и запуск планировщика задач
    scheduler = ScheduledTasks(bot, db, config)
    scheduler.start()

    # Запуск стартовых задач
    await scheduler.run_startup_tasks()

    try:
        # Запуск поллинга
        logger.info("Бот клуба X10 запущен")
        await dp.start_polling(bot)
    finally:
        # Остановка планировщика при завершении
        scheduler.shutdown()

        # Закрытие сессии бота
        await bot.session.close()
        logger.info("Бот клуба X10 остановлен")


# Middleware для передачи конфигурации и БД
class ConfigMiddleware:
    """
    Middleware для передачи конфигурации, базы данных и бота в хендлеры
    """

    def __init__(self, config, db, bot):
        self.config = config
        self.db = db
        self.bot = bot

    async def __call__(self, handler, event, data):
        # Добавляем объекты в data
        data["config"] = self.config
        data["db"] = self.db
        data["bot"] = self.bot

        # Продолжаем обработку
        return await handler(event, data)


# Создадим пакет handlers
import os

handlers_dir = 'handlers'
if not os.path.exists(handlers_dir):
    os.makedirs(handlers_dir)

    # Создаем файл __init__.py в папке handlers
    with open(os.path.join(handlers_dir, '__init__.py'), 'w') as f:
        f.write('"""Пакет с обработчиками бота."""\n')

# Запуск бота
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")