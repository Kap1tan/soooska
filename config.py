"""
Конфигурационный файл бота клуба X10.
Здесь хранятся все настройки и константы.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Импортируем данные из файла конфигурации
from config_data import *


@dataclass
class BotConfig:
    """Конфигурация бота"""
    token: str  # Токен бота
    admin_ids: List[int]  # Список ID администраторов
    group_id: int  # ID группы клуба X10
    channel_id: Optional[int] = None  # ID канала клуба X10 (опционально)


@dataclass
class DbConfig:
    """Конфигурация базы данных"""
    db_path: str  # Путь к файлу базы данных


@dataclass
class CryptoConfig:
    """Настройки криптовалютных платежей"""
    wallets: Dict[str, str]  # Адреса кошельков для разных криптовалют
    rates: Dict[str, float]  # Курсы обмена для криптовалют


@dataclass
class PaymentConfig:
    """Настройки платежей"""
    club_price: int = 1000  # Стоимость членства в клубе
    vietnam_tour_price: int = 1000  # Стоимость экскурсии по Вьетнаму
    consultation_price: int = 2000  # Стоимость консультации с основателем

    # Реквизиты для оплаты
    payment_details: Dict[str, str] = None

    # Настройки криптовалютных платежей
    crypto: Optional[CryptoConfig] = None


@dataclass
class ReferralConfig:
    """Настройки реферальной системы"""
    points_per_referral: int = 1000  # Баллы за приглашение одного друга
    free_days: int = 7  # Количество бесплатных дней для приглашенного

    # Бонусы за количество приглашенных
    bonus_levels: Dict[int, str] = None


@dataclass
class Config:
    """Общая конфигурация"""
    bot: BotConfig
    db: DbConfig
    payment: PaymentConfig
    referral: ReferralConfig


def load_config() -> Config:
    """Загрузка конфигурации из файла config_data.py"""
    return Config(
        bot=BotConfig(
            token=BOT_TOKEN,
            admin_ids=ADMIN_IDS,
            group_id=GROUP_ID,
        ),
        db=DbConfig(
            db_path=DB_PATH,
        ),
        payment=PaymentConfig(
            club_price=CLUB_PRICE,
            vietnam_tour_price=VIETNAM_TOUR_PRICE,
            consultation_price=CONSULTATION_PRICE,
            payment_details={
                "Карта РФ (Сбербанк)": CARD,
            },
            crypto=CryptoConfig(
                wallets=CRYPTO_WALLETS,
                rates=CRYPTO_RATES
            )
        ),
        referral=ReferralConfig(
            points_per_referral=POINTS_PER_REFERRAL,
            free_days=FREE_DAYS,
            bonus_levels=BONUS_LEVELS
        )
    )