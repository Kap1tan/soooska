"""
Обработчик мероприятий для бота клуба X10.
"""
import logging
import io
import qrcode
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from config import Config
from keyboards import (
    events_kb, payment_methods_kb, main_menu_kb, payment_confirmation_kb,
    stars_payment_kb, need_help_kb, crypto_currency_kb, crypto_payment_confirmation_kb
)
from utils import get_user_name, get_payment_description, parse_callback_data

router = Router()
logger = logging.getLogger(__name__)


# Определение состояний FSM
class EventStates(StatesGroup):
    """Состояния для обработки событий"""
    payment_confirmation = State()  # Подтверждение оплаты (загрузка скриншота)
    crypto_confirmation = State()  # Подтверждение оплаты криптой (ожидание транзакции)


@router.callback_query(F.data == "events")
async def callback_events(callback: CallbackQuery):
    """
    Обработчик кнопки "Мероприятия"
    """
    await callback.message.edit_text(
        "Выберите мероприятие:",
        reply_markup=events_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("event:"))
async def callback_event(callback: CallbackQuery, db: Database, config: Config):
    """
    Обработчик выбора мероприятия
    """
    event_type = callback.data.split(':')[1]

    if event_type == "vietnam":
        # Экскурсия по Вьетнаму
        event_title = "Экскурсия по Вьетнаму"
        event_description = (
            "VIP продукт - Экскурсия по Вьетнаму 🌴\n\n"
            "Эксклюзивная онлайн-экскурсия по самым интересным местам Вьетнама с нашим экспертом.\n\n"
            "Вы узнаете:\n"
            "- Секретные места, о которых не пишут в путеводителях\n"
            "- Как сэкономить на путешествии во Вьетнам\n"
            "- Культурные особенности и традиции местных жителей\n\n"
            "Длительность: 2 часа\n"
            "Формат: онлайн через Zoom\n"
            "Стоимость: 1000 рублей"
        )
    elif event_type == "consultation":
        # Консультация с основателем
        event_title = "Консультация с основателем"
        event_description = (
            "Персональная консультация с основателем Клуба Х10 🌟\n\n"
            "Это уникальная возможность:\n"
            "- Получить индивидуальный план развития\n"
            "- Решить конкретные задачи под руководством эксперта\n"
            "- Определить приоритеты и стратегии для достижения целей\n\n"
            "Длительность: 1 час\n"
            "Формат: онлайн через Zoom\n"
            "Стоимость: 2000 рублей"
        )
    else:
        # Неизвестное мероприятие
        await callback.message.edit_text(
            "Извините, данное мероприятие недоступно. Пожалуйста, выберите другое.",
            reply_markup=events_kb()
        )
        await callback.answer()
        return

    # Создаем инлайн-клавиатуру для оплаты
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", callback_data=f"pay_event:{event_type}")],
        [InlineKeyboardButton(text="Назад", callback_data="events")],
        [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
    ])

    await callback.message.edit_text(
        f"{event_title}\n\n{event_description}",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_event:"))
async def callback_pay_event(callback: CallbackQuery, db: Database, config: Config):
    """
    Обработчик оплаты мероприятия
    """
    event_type = callback.data.split(':')[1]

    await callback.message.edit_text(
        "Выберите способ оплаты:",
        reply_markup=payment_methods_kb(event_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_method:"))
async def callback_pay_method_event(callback: CallbackQuery, db: Database, config: Config):
    """
    Обработчик выбора способа оплаты для мероприятий
    """
    user_id = callback.from_user.id
    callback_data = parse_callback_data(callback.data)

    product_type = callback_data.get("product")
    payment_method = callback_data.get("method")

    if payment_method == "back":
        # Если нажата кнопка "Назад" в методах оплаты
        await callback.message.edit_text(
            "Выберите мероприятие:",
            reply_markup=events_kb()
        )
        await callback.answer()
        return

    if not product_type or not payment_method:
        await callback.message.edit_text(
            "Произошла ошибка при выборе способа оплаты. Пожалуйста, попробуйте снова.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    # Получаем описание платежа
    payment_info = get_payment_description(product_type, config)
    amount = payment_info["amount"]

    if payment_method == "crypto":
        # Выбор криптовалюты
        await callback.message.edit_text(
            f"Выберите криптовалюту для оплаты {payment_info['name']}:",
            reply_markup=crypto_currency_kb(product_type)
        )
        await callback.answer()
        return

    # Создаем запись о платеже в базе данных
    payment_id = await db.create_payment(
        user_id,
        amount,
        product_type,
        payment_method
    )

    if payment_method == "card":
        # Оплата на карту - предоставляем реквизиты
        payment_details = f"💳 Банковская карта: {config.payment.payment_details.get('Карта РФ (Сбербанк)')}"

        # Формируем сообщение для мероприятия
        message_text = (
            f"Реквизиты для оплаты:\n{payment_details}\n\n"
            f"Вы оплачиваете:\n"
            f"Сумма: {payment_info['amount']} рублей\n"
            f"Продукт: {payment_info['name']}\n"
            f"Тип платежа: Одноразовый\n\n"
            f"После оплаты: Нажмите кнопку 'Я оплатил' и отправьте скриншот оплаты, "
            f"менеджер расскажет о дальнейших шагах."
        )

        await callback.message.edit_text(
            message_text,
            reply_markup=payment_confirmation_kb(payment_id)
        )

    elif payment_method == "stars":
        # Оплата звездами Telegram
        # Конвертируем рубли в звезды (1000р = 750 звезд)
        stars_amount = int(amount * 0.75)  # 75% от суммы в рублях

        await callback.message.edit_text(
            f"Вы выбрали оплату Telegram Stars\n\n"
            f"Сумма: {stars_amount} ⭐ (эквивалент {amount} руб.)\n"
            f"Продукт: {payment_info['name']}\n\n"
            f"Нажмите кнопку 'Оплатить {stars_amount} ⭐' для продолжения."
        )

        # Отправляем инвойс для оплаты звездами
        await callback.message.answer_invoice(
            title=f"Оплата {payment_info['name']}",
            description=f"{payment_info['description']}",
            payload=f"payment_{payment_id}",
            provider_token="",  # Для Telegram Stars используем пустую строку
            currency="XTR",  # Валюта для Telegram Stars
            prices=[LabeledPrice(label=payment_info['name'], amount=stars_amount)],
            reply_markup=stars_payment_kb(stars_amount, payment_id)
        )

    await callback.answer()


@router.callback_query(F.data.startswith("crypto:"))
async def callback_crypto_currency_event(callback: CallbackQuery, bot: Bot, db: Database, config: Config):
    """
    Обработчик выбора криптовалюты для оплаты мероприятия
    """
    user_id = callback.from_user.id
    callback_data = callback.data.split(':')

    if len(callback_data) != 3:
        await callback.message.edit_text(
            "Произошла ошибка при выборе криптовалюты. Пожалуйста, попробуйте снова.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    product_type = callback_data[1]
    currency = callback_data[2]  # BTC, ETH, USDT, TRX

    # Получаем описание платежа
    payment_info = get_payment_description(product_type, config)
    amount_rub = payment_info["amount"]

    # Получаем курс и адрес кошелька для выбранной криптовалюты
    crypto_rate = config.payment.crypto.rates.get(currency, 0)
    wallet_address = config.payment.crypto.wallets.get(currency, "")

    if crypto_rate == 0 or not wallet_address:
        await callback.message.edit_text(
            "Извините, выбранная криптовалюта временно недоступна для оплаты. Пожалуйста, выберите другой способ оплаты.",
            reply_markup=payment_methods_kb(product_type)
        )
        await callback.answer()
        return

    # Рассчитываем сумму в криптовалюте
    crypto_amount = round(amount_rub / crypto_rate, 8)

    # Создаем запись о платеже в базе данных
    payment_method = f"crypto_{currency}"
    payment_id = await db.create_payment(
        user_id,
        amount_rub,
        product_type,
        payment_method
    )

    # Создаем QR-код с адресом кошелька
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(wallet_address)
    qr.make(fit=True)

    # Создаем изображение QR-кода
    img = qr.make_image(fill_color="black", back_color="white")

    # Преобразуем изображение в байты для отправки
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)

    # Отправляем QR-код для оплаты
    qr_file = BufferedInputFile(img_byte_arr.getvalue(), filename=f"payment_{payment_id}_qr.png")

    # Отправляем информацию о платеже с QR-кодом
    await callback.message.answer_photo(
        photo=qr_file,
        caption=(
            f"Оплата {payment_info['name']} криптовалютой {currency}\n\n"
            f"Сумма: {crypto_amount} {currency} (≈{amount_rub} руб.)\n"
            f"Адрес кошелька: `{wallet_address}`\n\n"
            f"1. Переведите точную сумму {crypto_amount} {currency} на указанный адрес\n"
            f"2. После отправки платежа нажмите кнопку 'Я оплатил'\n"
            f"3. В сообщении укажите ID транзакции (TxID)\n\n"
            f"Внимание: оплата будет проверена администратором."
        ),
        reply_markup=crypto_payment_confirmation_kb(payment_id)
    )

    # Редактируем предыдущее сообщение
    await callback.message.edit_text(
        f"Выбрана оплата криптовалютой {currency}. QR-код для оплаты отправлен ниже.",
        reply_markup=main_menu_kb()
    )

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_crypto:"))
async def callback_confirm_crypto_event(callback: CallbackQuery, state: FSMContext, db: Database, config: Config):
    """
    Обработчик подтверждения оплаты криптовалютой для мероприятий
    """
    payment_id = int(callback.data.split(':')[1])

    # Получаем информацию о платеже
    payment = await db.get_payment(payment_id)

    if not payment:
        # Отправляем новое сообщение вместо редактирования
        await callback.message.answer(
            "Платеж не найден. Пожалуйста, попробуйте снова или обратитесь к менеджеру.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    # Устанавливаем состояние для ожидания ID транзакции
    await state.set_state(EventStates.crypto_confirmation)
    await state.update_data(payment_id=payment_id)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Пожалуйста, отправьте ID транзакции (TxID) для проверки вашего платежа.\n\n"
        "Вы можете найти TxID в истории транзакций вашего криптокошелька или биржи."
    )

    await callback.answer()


@router.message(EventStates.crypto_confirmation)
async def process_crypto_confirmation_event(message: Message, state: FSMContext, db: Database, config: Config):
    """
    Обработчик получения ID транзакции для криптоплатежа мероприятия
    """
    data = await state.get_data()
    payment_id = data.get('payment_id')

    # Проверяем, есть ли текст сообщения (TxID)
    if not message.text:
        await message.answer(
            "Пожалуйста, отправьте текстовое сообщение с ID транзакции (TxID).\n\n"
            "Если у вас возникли сложности, вы можете связаться с менеджером.",
            reply_markup=need_help_kb()
        )
        return

    # Получаем информацию о платеже
    payment = await db.get_payment(payment_id)

    if not payment:
        await message.answer(
            "Платеж не найден. Пожалуйста, попробуйте снова или обратитесь к менеджеру.",
            reply_markup=main_menu_kb()
        )
        await state.clear()
        return

    tx_id = message.text.strip()
    current_payment_method = payment.get('payment_method', '')

    # Обновляем информацию о платеже, добавляя TxID к значению метода оплаты
    conn = await db.get_conn()
    try:
        new_payment_method = f"{current_payment_method}_TxID:{tx_id}"
        await conn.execute(
            "UPDATE payments SET payment_method = ? WHERE payment_id = ?",
            (new_payment_method, payment_id)
        )
        await conn.commit()
    finally:
        await conn.close()

    # Уведомляем пользователя о получении TxID
    await message.answer(
        "Спасибо! Ваш ID транзакции получен и отправлен на проверку.\n\n"
        "Как только платеж будет подтвержден, с вами свяжется менеджер для предоставления дополнительной информации.\n"
        "Обычно проверка занимает не более 24 часов.",
        reply_markup=main_menu_kb()
    )

    # Отправляем информацию о платеже администраторам для подтверждения
    for admin_id in config.bot.admin_ids:
        try:
            # Формируем информацию о платеже
            payment_method = payment.get('payment_method', '')

            # Получаем тип криптовалюты
            currency = payment_method.split('_')[1] if '_' in payment_method else 'Unknown'

            # Получаем информацию о пользователе
            user_id = payment.get('user_id')
            user = await db.get_user(user_id)
            username = user.get('username', '') if user else ''
            first_name = user.get('first_name', '') if user else ''
            last_name = user.get('last_name', '') if user else ''

            # Формируем ссылку на пользователя
            user_link = f"@{username}" if username else f"tg://user?id={user_id}"
            user_display = f"{first_name} {last_name}".strip() or f"Пользователь {user_id}"

            admin_notification = (
                f"💰 Новый криптоплатеж за мероприятие ожидает подтверждения\n\n"
                f"Платеж ID: {payment_id}\n"
                f"Пользователь: {user_display}\n"
                f"Ссылка: {user_link}\n"
                f"ID пользователя: {user_id}\n"
                f"Мероприятие: {payment.get('product_type')}\n"
                f"Сумма: {payment.get('amount')} руб.\n"
                f"Криптовалюта: {currency}\n"
                f"TxID: {tx_id}\n\n"
                f"Для подтверждения используйте команду: /confirm_payment_{payment_id}"
            )

            await message.bot.send_message(
                chat_id=admin_id,
                text=admin_notification
            )

            logger.info(f"Уведомление о криптоплатеже мероприятия {payment_id} отправлено администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")

    # Сбрасываем состояние
    await state.clear()


@router.callback_query(F.data == "cancel_payment")
async def callback_cancel_payment_event(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик отмены оплаты
    """
    await state.clear()

    # Всегда отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Оплата отменена. Выберите нужное действие:",
        reply_markup=main_menu_kb()
    )

    await callback.answer()


@router.callback_query(F.data.startswith("confirm_payment:"))
async def callback_confirm_payment_event(callback: CallbackQuery, state: FSMContext, db: Database, config: Config):
    """
    Обработчик подтверждения оплаты для мероприятий
    """
    payment_id = int(callback.data.split(':')[1])

    # Получаем информацию о платеже
    payment = await db.get_payment(payment_id)

    if not payment:
        # Отправляем новое сообщение вместо редактирования
        await callback.message.answer(
            "Платеж не найден. Пожалуйста, попробуйте снова или обратитесь к менеджеру.",
            reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    # Для мероприятий - запрашиваем скриншот для подтверждения
    await state.set_state(EventStates.payment_confirmation)
    await state.update_data(payment_id=payment_id)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Пожалуйста, отправьте скриншот оплаты для подтверждения.\n\n"
        "Наш менеджер проверит его и свяжется с вами для предоставления дополнительной информации."
    )

    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler_event(pre_checkout_query: PreCheckoutQuery):
    """
    Обработчик предварительной проверки платежа для мероприятий
    """
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler_event(message: Message, db: Database, config: Config):
    """
    Обработчик успешного платежа звездами для мероприятий
    """
    payment_payload = message.successful_payment.invoice_payload

    # Извлекаем ID платежа из payload
    if payment_payload.startswith("payment_"):
        payment_id = int(payment_payload.split("_")[1])

        # Получаем информацию о платеже
        payment = await db.get_payment(payment_id)

        if not payment:
            await message.answer(
                "Произошла ошибка при обработке платежа. Пожалуйста, обратитесь к менеджеру.",
                reply_markup=main_menu_kb()
            )
            return

        user_id = payment.get('user_id')
        product_type = payment.get('product_type')

        # Подтверждаем платеж
        await db.confirm_payment(payment_id)

        # Для мероприятий
        await message.answer(
            "Спасибо за оплату! 🎉\n\n"
            "Ваш платеж успешно обработан.\n"
            "В ближайшее время с вами свяжется менеджер для предоставления доступа к мероприятию.",
            reply_markup=main_menu_kb()
        )

        # Уведомляем администраторов о новом платеже
        for admin_id in config.bot.admin_ids:
            try:
                # Получаем информацию о пользователе
                user = await db.get_user(user_id)
                username = user.get('username', '') if user else ''
                first_name = user.get('first_name', '') if user else ''
                last_name = user.get('last_name', '') if user else ''

                # Формируем ссылку на пользователя
                user_link = f"@{username}" if username else f"tg://user?id={user_id}"
                user_display = f"{first_name} {last_name}".strip() or f"Пользователь {user_id}"

                await message.bot.send_message(
                    admin_id,
                    f"Новый платеж звездами за мероприятие\n\n"
                    f"Пользователь: {user_display}\n"
                    f"Ссылка: {user_link}\n"
                    f"ID пользователя: {user_id}\n"
                    f"Мероприятие: {product_type}\n"
                    f"Сумма: {payment.get('amount')} руб. ({int(payment.get('amount') * 0.75)} звезд)\n"
                    f"Статус: Подтвержден"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")


@router.message(EventStates.payment_confirmation)
async def process_event_payment_confirmation(message: Message, state: FSMContext, db: Database, config: Config):
    """
    Обработчик получения скриншота подтверждения оплаты мероприятия
    """
    data = await state.get_data()
    payment_id = data.get('payment_id')

    # Проверяем наличие фото или документа
    if not message.photo and not message.document:
        await message.answer(
            "Пожалуйста, отправьте скриншот оплаты в виде фото или документа.\n\n"
            "Если у вас возникли сложности, вы можете связаться с менеджером.",
            reply_markup=need_help_kb()
        )
        return

    # Получаем информацию о платеже
    payment = await db.get_payment(payment_id)

    if not payment:
        await message.answer(
            "Платеж не найден. Пожалуйста, попробуйте снова или обратитесь к менеджеру.",
            reply_markup=main_menu_kb()
        )
        await state.clear()
        return

    # Уведомляем пользователя о получении скриншота
    await message.answer(
        "Спасибо! Ваш скриншот отправлен на проверку.\n\n"
        "Как только платеж будет подтвержден, вы получите доступ к мероприятию.\n"
        "Наш менеджер свяжется с вами для предоставления дополнительной информации.",
        reply_markup=main_menu_kb()
    )

    # Отправляем скриншот и информацию о платеже администраторам для подтверждения
    for admin_id in config.bot.admin_ids:
        try:
            # Получаем информацию о пользователе
            user_id = message.from_user.id
            user = await db.get_user(user_id)
            username = user.get('username', '') if user else message.from_user.username
            first_name = user.get('first_name', '') if user else message.from_user.first_name
            last_name = user.get('last_name', '') if user else message.from_user.last_name

            # Формируем ссылку на пользователя
            user_link = f"@{username}" if username else f"tg://user?id={user_id}"
            user_display = f"{first_name} {last_name}".strip() or f"Пользователь {user_id}"

            # Формируем подпись к скриншоту
            caption = (
                f"Скриншот оплаты мероприятия\n\n"
                f"Пользователь: {user_display}\n"
                f"Ссылка: {user_link}\n"
                f"ID пользователя: {user_id}\n"
                f"Платеж ID: {payment_id}\n"
                f"Мероприятие: {payment.get('product_type')}\n"
                f"Сумма: {payment.get('amount')} рублей\n\n"
                f"Для подтверждения платежа используйте команду: /confirm_payment_{payment_id}"
            )

            # Пересылаем скриншот администратору
            if message.photo:
                await message.bot.send_photo(
                    chat_id=admin_id,
                    photo=message.photo[-1].file_id,
                    caption=caption
                )
            elif message.document:
                await message.bot.send_document(
                    chat_id=admin_id,
                    document=message.document.file_id,
                    caption=caption
                )

            logger.info(f"Скриншот оплаты мероприятия отправлен администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администратору {admin_id} о платеже мероприятия: {e}")

    # Сбрасываем состояние
    await state.clear()


# Импортируем в конце, чтобы избежать циклических импортов
from keyboards import need_help_kb