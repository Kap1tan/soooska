"""
Обработчик функций клуба X10 для бота.
"""
import logging
import io
import qrcode
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, FSInputFile, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import Database
from config import Config
from keyboards import (
    club_menu_kb, payment_methods_kb, payment_confirmation_kb, crypto_currency_kb,
    extend_subscription_kb, club_access_kb, main_menu_kb, crypto_payment_confirmation_kb,
    stars_payment_kb, need_help_kb
)
from utils import get_user_name, get_payment_description, parse_callback_data, check_user_in_group

router = Router()
logger = logging.getLogger(__name__)


# Определение состояний FSM
class ClubStates(StatesGroup):
    """Состояния для обработки действий с клубом"""
    payment_confirmation = State()  # Подтверждение оплаты (загрузка скриншота)
    crypto_confirmation = State()   # Подтверждение оплаты криптой (ожидание транзакции)


@router.callback_query(F.data == "club")
async def callback_club(callback: CallbackQuery, db: Database):
    """
    Обработчик кнопки "Клуб Х10"
    """
    user_id = callback.from_user.id

    # Проверяем наличие активной подписки
    subscription = await db.check_subscription(user_id)

    if subscription:
        # У пользователя есть активная подписка
        from datetime import datetime
        end_date = subscription.get('end_date')
        if end_date:
            end_date_obj = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            days_left = (end_date_obj - datetime.now()).days

            await callback.message.edit_text(
                f"Добро пожаловать в Клуб Х10!\n\n"
                f"У вас активная подписка.\n"
                f"Дней осталось: {days_left}\n\n"
                f"Вы можете войти в клуб, нажав на кнопку ниже:",
                reply_markup=club_access_kb()
            )
        else:
            await callback.message.edit_text(
                "Добро пожаловать в Клуб Х10!",
                reply_markup=club_menu_kb()
            )
    else:
        # У пользователя нет активной подписки
        await callback.message.edit_text(
            "Добро пожаловать в Клуб Х10!\n\n"
            "Для доступа к клубу необходимо оплатить членство.\n"
            "Стоимость: 1000 рублей на 1 месяц\n\n"
            "Выберите действие:",
            reply_markup=club_menu_kb()
        )

    await callback.answer()


@router.callback_query(F.data == "pay_club")
async def callback_pay_club(callback: CallbackQuery, db: Database, config: Config):
    """
    Обработчик кнопки "Оплатить доступ"
    """
    await callback.message.edit_text(
        "Выберите способ оплаты:",
        reply_markup=payment_methods_kb("club")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_method:"))
async def callback_pay_method(callback: CallbackQuery, db: Database, config: Config):
    """
    Обработчик выбора способа оплаты
    """
    user_id = callback.from_user.id
    callback_data = parse_callback_data(callback.data)

    product_type = callback_data.get("product")
    payment_method = callback_data.get("method")

    if payment_method == "back":
        # Если нажата кнопка "Назад" в методах оплаты
        await callback.message.edit_text(
            "Выберите действие:",
            reply_markup=club_menu_kb()
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

        if product_type == "club":
            # Для клуба - автоматическая оплата
            message_text = (
                f"Вы оплачиваете:\n"
                f"Сумма: {payment_info['amount']} рублей\n"
                f"Доступ: {payment_info['name']} на {payment_info['days']} дней\n"
                f"Тип платежа: Одноразовый\n\n"
                f"После оплаты будет предоставлен доступ: {payment_info['description']}\n\n"
                f"Для оплаты используйте следующие реквизиты:\n{payment_details}\n\n"
                f"После оплаты нажмите кнопку 'Я оплатил' и отправьте скриншот платежа."
            )
        else:
            # Для мероприятий - оплата с подтверждением скриншота
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
            currency="XTR",    # Валюта для Telegram Stars
            prices=[LabeledPrice(label=payment_info['name'], amount=stars_amount)],
            reply_markup=stars_payment_kb(stars_amount, payment_id)
        )

    await callback.answer()


@router.callback_query(F.data.startswith("crypto:"))
async def callback_crypto_currency(callback: CallbackQuery, bot: Bot, db: Database, config: Config):
    """
    Обработчик выбора криптовалюты для оплаты
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
async def callback_confirm_crypto(callback: CallbackQuery, state: FSMContext, db: Database, config: Config):
    """
    Обработчик подтверждения оплаты криптовалютой
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
    await state.set_state(ClubStates.crypto_confirmation)
    await state.update_data(payment_id=payment_id)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Пожалуйста, отправьте ID транзакции (TxID) для проверки вашего платежа.\n\n"
        "Вы можете найти TxID в истории транзакций вашего криптокошелька или биржи."
    )

    await callback.answer()


@router.message(ClubStates.crypto_confirmation)
async def process_crypto_confirmation(message: Message, state: FSMContext, db: Database, config: Config):
    """
    Обработчик получения ID транзакции для криптоплатежа
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
        "Как только платеж будет подтвержден, вы получите доступ к продукту.\n"
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

            admin_notification = (
                f"💰 Новый криптоплатеж ожидает подтверждения\n\n"
                f"Платеж ID: {payment_id}\n"
                f"Пользователь: {first_name} {last_name} ({user_link})\n"
                f"ID пользователя: {user_id}\n"
                f"Продукт: {payment.get('product_type')}\n"
                f"Сумма: {payment.get('amount')} руб.\n"
                f"Криптовалюта: {currency}\n"
                f"TxID: {tx_id}\n\n"
                f"Для подтверждения используйте команду: /confirm_payment_{payment_id}"
            )

            await message.bot.send_message(
                chat_id=admin_id,
                text=admin_notification
            )

            logger.info(f"Уведомление о криптоплатеже {payment_id} отправлено администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")

    # Сбрасываем состояние
    await state.clear()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """Обработчик предварительной проверки платежа"""
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, db: Database, config: Config):
    """Обработчик успешного платежа звездами"""
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

        if product_type == "club":
            # Добавляем подписку на месяц
            payment_info = get_payment_description(product_type, config)
            await db.add_subscription(user_id, payment_info["days"])

            # Отправляем сообщение об успешной оплате
            await message.answer(
                "Спасибо за оплату! 🎉\n\n"
                "Ваш доступ к клубу X10 активирован.\n\n"
                "Теперь вы можете присоединиться к клубу, нажав на кнопку ниже:",
                reply_markup=club_access_kb()
            )
        else:
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
                        f"Новый платеж звездами от пользователя {user_display}\n"
                        f"Ссылка: {user_link}\n"
                        f"ID пользователя: {user_id}\n"
                        f"Продукт: {product_type}\n"
                        f"Сумма: {payment.get('amount')} руб. ({int(payment.get('amount') * 0.75)} звезд)\n"
                        f"Статус: Подтвержден"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")


@router.callback_query(F.data.startswith("confirm_payment:"))
async def callback_confirm_payment(callback: CallbackQuery, state: FSMContext, db: Database, config: Config):
    """
    Обработчик подтверждения оплаты
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

    user_id = payment.get('user_id')
    product_type = payment.get('product_type')
    payment_method = payment.get('payment_method')

    # Для карточных платежей - запрашиваем скриншот
    await state.set_state(ClubStates.payment_confirmation)
    await state.update_data(payment_id=payment_id)

    # Отправляем новое сообщение вместо редактирования
    await callback.message.answer(
        "Пожалуйста, отправьте скриншот оплаты для подтверждения.\n\n"
        "Наш менеджер проверит его и предоставит вам доступ."
    )

    await callback.answer()


@router.message(ClubStates.payment_confirmation)
async def process_payment_confirmation(message: Message, state: FSMContext, db: Database, config: Config):
    """
    Обработчик получения скриншота подтверждения оплаты
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
        "Как только платеж будет подтвержден, вы получите доступ к продукту.\n"
        "Обычно проверка занимает не более 24 часов.",
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
                f"Скриншот оплаты от пользователя {user_display}\n"
                f"Ссылка: {user_link}\n"
                f"ID пользователя: {user_id}\n"
                f"Платеж ID: {payment_id}\n"
                f"Продукт: {payment.get('product_type')}\n"
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

            logger.info(f"Скриншот оплаты отправлен администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")

    # Сбрасываем состояние
    await state.clear()


@router.callback_query(F.data == "cancel_payment")
async def callback_cancel_payment(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик отмены оплаты
    """
    await state.clear()

    try:
        # Пробуем отредактировать сообщение
        await callback.message.edit_text(
            "Оплата отменена. Выберите нужное действие:",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        # В случае ошибки (например, сообщение нельзя редактировать)
        # отправляем новое сообщение вместо редактирования
        await callback.message.answer(
            "Оплата отменена. Выберите нужное действие:",
            reply_markup=main_menu_kb()
        )

    await callback.answer()


@router.callback_query(F.data == "extend_subscription")
async def callback_extend_subscription(callback: CallbackQuery):
    """
    Обработчик кнопки продления подписки
    """
    await callback.message.edit_text(
        "Для продления подписки выберите способ оплаты:",
        reply_markup=payment_methods_kb("club")
    )
    await callback.answer()


@router.callback_query(F.data == "not_now")
async def callback_not_now(callback: CallbackQuery):
    """
    Обработчик кнопки "Не сейчас" при напоминании о продлении подписки
    """
    await callback.message.edit_text(
        "Хорошо, вы можете продлить подписку позже в главном меню.",
        reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "join_club")
async def callback_join_club(callback: CallbackQuery, bot: Bot, db: Database, config: Config):
    """
    Обработчик кнопки "Войти" в клуб
    """
    user_id = callback.from_user.id

    # Проверяем наличие активной подписки
    subscription = await db.check_subscription(user_id)

    if not subscription:
        await callback.message.edit_text(
            "У вас нет активной подписки на клуб X10.\n"
            "Для доступа необходимо оплатить членство.",
            reply_markup=club_menu_kb()
        )
        await callback.answer()
        return

    # Проверяем, находится ли пользователь в группе
    is_in_group = await check_user_in_group(bot, config, user_id)

    if is_in_group:
        await callback.message.edit_text(
            "Вы уже состоите в группе клуба X10.\n"
            "Если у вас возникли проблемы с доступом, обратитесь к менеджеру.",
            reply_markup=main_menu_kb()
        )
    else:
        # Отправляем пользователю ссылку на группу
        try:
            # Создаем приглашение на 1 использование, действительное в течение суток
            from datetime import datetime, timedelta
            invite_link = await bot.create_chat_invite_link(
                chat_id=config.bot.group_id,
                creates_join_request=False,
                name=f"Invite for {user_id}",
                expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
                member_limit=1
            )

            await callback.message.edit_text(
                "Поздравляем! Вы получили доступ к клубу X10.\n\n"
                "Нажмите на кнопку ниже, чтобы присоединиться к группе:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Присоединиться к группе", url=invite_link.invite_link)],
                    [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка при создании пригласительной ссылки: {e}")
            await callback.message.edit_text(
                "Произошла ошибка при создании пригласительной ссылки.\n"
                "Пожалуйста, обратитесь к менеджеру для получения доступа.",
                reply_markup=need_help_kb()
            )

    await callback.answer()


@router.callback_query(F.data == "access_club")
async def callback_access_club(callback: CallbackQuery, bot: Bot, db: Database, config: Config):
    """
    Обработчик кнопки "ВОЙТИ" (доступ к клубу)
    """
    user_id = callback.from_user.id

    # Проверяем наличие активной подписки
    subscription = await db.check_subscription(user_id)

    if not subscription:
        await callback.message.edit_text(
            "У вас нет активной подписки на клуб X10.\n"
            "Для доступа необходимо оплатить членство.",
            reply_markup=club_menu_kb()
        )
        await callback.answer()
        return

    # Создаем приглашение в группу
    try:
        # Создаем приглашение на 1 использование, действительное в течение суток
        from datetime import datetime, timedelta
        invite_link = await bot.create_chat_invite_link(
            chat_id=config.bot.group_id,
            creates_join_request=False,
            name=f"Invite for {user_id}",
            expire_date=int((datetime.now() + timedelta(days=1)).timestamp()),
            member_limit=1
        )

        await callback.message.edit_text(
            "Поздравляем! Вы получили доступ к клубу X10.\n\n"
            "Нажмите на кнопку ниже, чтобы присоединиться к группе:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Присоединиться к группе", url=invite_link.invite_link)],
                [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка при создании пригласительной ссылки: {e}")
        await callback.message.edit_text(
            "Произошла ошибка при создании пригласительной ссылки.\n"
            "Пожалуйста, обратитесь к менеджеру для получения доступа.",
            reply_markup=need_help_kb()
        )

    await callback.answer()


@router.callback_query(F.data == "learn_more")
async def callback_learn_more(callback: CallbackQuery):
    """
    Обработчик кнопки "Узнать больше"
    """
    # Создаем инлайн-клавиатуру с кнопками оплаты и возврата
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить доступ", callback_data="pay_club")],
        [InlineKeyboardButton(text="Назад", callback_data="club")],
        [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")]
    ])

    await callback.message.edit_text(
        "Клуб Х10 - это сообщество единомышленников, стремящихся к развитию и росту.\n\n"
        "Преимущества членства в клубе:\n"
        "- Доступ к закрытому чату с экспертами\n"
        "- Еженедельные вебинары на актуальные темы\n"
        "- Участие в мастер-классах и воркшопах\n"
        "- Нетворкинг с интересными людьми\n\n"
        "Стоимость: 1000 рублей в месяц",
        reply_markup=markup
    )
    await callback.answer()


# Импортируем в конце, чтобы избежать циклических импортов
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton