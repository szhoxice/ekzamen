"""
Простой Telegram-бот с приветствием.
Запуск: установите BOT_TOKEN и выполните python bot.py
"""

import logging
import os
import time
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.request import HTTPXRequest

from questions import QUESTION_TEXTS
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def telegram_http_request() -> HTTPXRequest:
    """HTTP-клиент с увеличенными таймаутами (по умолчанию в PTB — 5 с, часто не хватает).

    TELEGRAM_PROXY — опционально, например http://127.0.0.1:7890 или socks5://127.0.0.1:1080
    (для SOCKS: pip install "python-telegram-bot[socks]").
    """
    connect = float(os.environ.get("TELEGRAM_CONNECT_TIMEOUT", "60"))
    read_t = float(os.environ.get("TELEGRAM_READ_TIMEOUT", "60"))
    write_t = float(os.environ.get("TELEGRAM_WRITE_TIMEOUT", "60"))
    proxy = os.environ.get("TELEGRAM_PROXY")
    kwargs = {
        "connect_timeout": connect,
        "read_timeout": read_t,
        "write_timeout": write_t,
        "pool_timeout": 10.0,
    }
    if proxy:
        kwargs["proxy"] = proxy.strip()
    return HTTPXRequest(**kwargs)


TG_MAX_MESSAGE = 4096


def split_telegram_message(text: str, max_len: int = TG_MAX_MESSAGE) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= max_len:
            parts.append(rest)
            break
        chunk = rest[:max_len]
        nl = chunk.rfind("\n")
        if nl > max_len * 2 // 3:
            parts.append(rest[: nl + 1].rstrip())
            rest = rest[nl + 1 :]
        else:
            parts.append(rest[:max_len])
            rest = rest[max_len:]
    return parts


async def send_question_reply(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    chunks = split_telegram_message(text)
    chat_id = query.message.chat_id if query.message else query.from_user.id
    for i, part in enumerate(chunks):
        if i == 0 and query.message:
            await query.message.reply_text(part)
        else:
            await context.bot.send_message(chat_id=chat_id, text=part)


def greeting_text(first_name: Optional[str]) -> str:
    name = first_name or "друг"
    return f"Привет, {name}! 👋"


def questions_prompt_text() -> str:
    return "Выбери номер вопроса (1–40):"


def bottom_start_keyboard() -> ReplyKeyboardMarkup:
    """Кнопка отправляет текст /start — срабатывает команда и снова показывает меню."""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("/start")]],
        resize_keyboard=True,
    )


QUESTION_COUNT = 40
QUESTIONS_PER_ROW = 5


def question_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for row_start in range(0, QUESTION_COUNT, QUESTIONS_PER_ROW):
        row = [
            InlineKeyboardButton(str(i), callback_data=f"question_{i}")
            for i in range(row_start + 1, min(row_start + 1 + QUESTIONS_PER_ROW, QUESTION_COUNT + 1))
        ]
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def send_main_menu(update: Update) -> None:
    """Два сообщения: reply-клавиатура с /start и inline-сетка вопросов (в одном сообщении их совместить нельзя)."""
    user = update.effective_user
    name = user.first_name if user else None
    await update.message.reply_text(
        greeting_text(name),
        reply_markup=bottom_start_keyboard(),
    )
    await update.message.reply_text(
        questions_prompt_text(),
        reply_markup=question_keyboard(),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update)


async def on_question_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    suffix = query.data.removeprefix("question_")
    body = QUESTION_TEXTS.get(suffix)
    if body:
        await query.answer()
        await send_question_reply(query, context, body)
        return

    await query.answer("Вопрос не найден.")


async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_menu(update)


RETRY_DELAY_SEC = 5


def build_application(token: str) -> Application:
    http = telegram_http_request()
    app = (
        Application.builder()
        .token(token)
        .request(http)
        .get_updates_request(http)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_question_click, pattern=r"^question_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    return app


def main() -> None:
    load_dotenv()
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Укажите токен бота в переменной окружения BOT_TOKEN.\n"
            "Токен выдаёт @BotFather в Telegram."
        )

    while True:
        try:
            app = build_application(token)
            logger.info("Бот запущен")
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except KeyboardInterrupt:
            logger.info("Остановка (Ctrl+C)")
            raise
        except SystemExit:
            raise
        except Exception as e:
            logger.warning(
                "Ошибка, перезапуск через %s с: %s: %s",
                RETRY_DELAY_SEC,
                type(e).__name__,
                e,
                exc_info=True,
            )
            time.sleep(RETRY_DELAY_SEC)


if __name__ == "__main__":
    main()
