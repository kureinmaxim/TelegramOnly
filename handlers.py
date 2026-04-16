# -*- coding: utf-8 -*-
"""
Упрощённые обработчики команд бота с поддержкой VLESS-Reality.

Этот модуль содержит минимальный набор команд:
- Базовые: start, help, info, clear
- Админские: ver, api, gen_api_key, del_api_key, encryption_key, gen_encryption_key,
             del_encryption_key, gen_chacha_key, gen_pqc_key
- Управление пользователями: list_users, setcity, setgreeting, special_add, special_remove
- Настройки ИИ: ai_provider, ch_model
- VLESS-Reality: vless_status, vless_on, vless_off, vless_config, vless_set_*, vless_gen_keys, vless_test
"""

import logging
import os
import secrets
import base64
import json
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config
from storage import (
    get_user_city,
    set_user_city,
    get_user_greeting,
    set_user_greeting,
    is_special_user as storage_is_special_user,
    add_special_user,
    remove_special_user,
    list_users as storage_list_users,
)
from utils import (
    format_user_info,
    escape_markdown,
    get_app_version,
    get_available_models,
    get_current_model,
    set_current_model,
)
import vless_manager
import hysteria2_manager
import mtproto_manager
import headscale_manager
import naiveproxy_manager
import tuic_manager
import anytls_manager
import xhttp_manager
import telegram_capsule_export

logger = logging.getLogger(__name__)


class BotHandlersLite:
    """Упрощённый класс обработчиков бота с поддержкой VLESS-Reality."""
    
    def __init__(self, config: Config = None):
        """Инициализация обработчиков."""
        self.config = config

    async def _reply_export_file(self, message, content: str, filename: str, caption: str):
        """Отправить экспорт как файл, чтобы не упираться в лимиты/MarkdownV2."""
        buffer = BytesIO(content.encode("utf-8"))
        buffer.name = filename
        await message.reply_document(document=buffer, caption=caption)
    
    def _is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором."""
        if not self.config:
            return False
        return self.config.is_admin(user_id)

    def _secret_reveal_allowed(self) -> bool:
        """Разрешён ли полный вывод секретов через удалённые каналы."""
        return os.getenv("TELEGRAMONLY_ALLOW_SECRET_REVEAL", "").strip().lower() in {
            "1", "true", "yes", "on"
        }

    def _mask_secret(self, value: str) -> str:
        """Вернуть безопасное маскированное представление секрета."""
        if not value:
            return "***"
        if len(value) <= 12:
            return "***"
        return f"{value[:8]}...{value[-4:]}"

    async def _reply_vless_qr(self, message, name_or_uuid: str):
        """Отправить QR и ссылку для VLESS-клиента."""
        success, response, payload = vless_manager.build_client_qr_payload(name_or_uuid)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"vless-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для VLESS-клиента {payload['name']}",
        )
        await message.reply_text(
            "📲 VLESS QR для клиента {name}\n\n"
            "UUID: {uuid}\n\n"
            "Ссылка для импорта:\n{link}\n\n"
            "FoXray: Import/Scan QR -> наведи камеру на код или импортируй ссылку напрямую.".format(
                name=payload["name"],
                uuid=payload["uuid"],
                link=payload["link"],
            )
        )
        return True

    async def _show_vless_qr_selection(self, message):
        """Показать inline-меню выбора клиента для QR."""
        clients = vless_manager.list_clients()
        if not clients:
            await message.reply_text("❌ Список клиентов пуст. Сначала используйте /vless_add_client")
            return

        keyboard = []
        for client in clients:
            client_name = client.get("name") or "client"
            client_uuid = client.get("uuid") or ""
            if not client_uuid:
                continue
            keyboard.append([
                InlineKeyboardButton(
                    f"📷 {client_name}",
                    callback_data=f"vless_export_qr_uuid:{client_uuid}",
                )
            ])

        if not keyboard:
            await message.reply_text("❌ У клиентов нет UUID для генерации QR")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("Выберите клиента для показа QR:", reply_markup=reply_markup)

    async def _reply_hy2_qr(self, message, name_or_password: str):
        """Отправить QR и URI для Hysteria2-клиента."""
        success, response, payload = hysteria2_manager.build_client_qr_payload(name_or_password)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"hy2-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для Hysteria2-клиента {payload['name']}",
        )
        await message.reply_text(
            "⚡ Hysteria2 QR для клиента {name}\n\n"
            "Пароль: {password}\n\n"
            "URI для импорта:\n{uri}\n\n"
            "Поддерживаемый клиент может импортировать профиль по QR или напрямую по hy2:// ссылке.".format(
                name=payload["name"],
                password=payload["password"],
                uri=payload["uri"],
            )
        )
        return True

    async def _show_hy2_qr_selection(self, message):
        """Показать inline-меню выбора клиента Hysteria2 для QR."""
        clients = hysteria2_manager.list_clients()
        if not clients:
            await message.reply_text("❌ Список клиентов пуст. Сначала используйте /hy2_add_client")
            return

        keyboard = []
        for client in clients:
            client_name = client.get("name") or "client"
            client_password = client.get("password") or ""
            if not client_password:
                continue
            keyboard.append([
                InlineKeyboardButton(
                    f"📷 {client_name}",
                    callback_data=f"hy2_export_qr_pw:{client_password}",
                )
            ])

        if not keyboard:
            await message.reply_text("❌ У клиентов нет пароля для генерации QR")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("Выберите Hysteria2-клиента для показа QR:", reply_markup=reply_markup)

    async def _reply_mt_qr(self, message, name_or_secret: str):
        """Отправить QR и ссылки для MTProto-клиента."""
        success, response, payload = mtproto_manager.build_client_qr_payload(name_or_secret)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"mtproto-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для MTProto-клиента {payload['name']}",
        )
        await message.reply_text(
            "📡 MTProto QR для клиента {name}\n\n"
            "Режим: {mode}\n\n"
            "Secret: {secret}\n\n"
            "HTTPS link:\n{https_link}\n\n"
            "tg:// link:\n{tg_link}\n\n"
            "Для QR используется HTTPS-ссылка, чтобы камера телефона надёжнее открывала Telegram.".format(
                name=payload["name"],
                mode=payload.get("secret_mode_label", "unknown"),
                secret=payload["secret"],
                https_link=payload["https_link"],
                tg_link=payload["tg_link"],
            )
        )
        return True

    async def _show_mt_qr_selection(self, message):
        """Показать inline-меню выбора MTProto-клиента для QR."""
        clients = mtproto_manager.list_clients()
        if not clients:
            await message.reply_text("❌ Список клиентов пуст. Сначала используйте /mt_add_client")
            return

        keyboard = []
        for client in clients:
            client_name = client.get("name") or "client"
            client_secret = client.get("secret") or ""
            if not client_secret:
                continue
            keyboard.append([
                InlineKeyboardButton(
                    f"📷 {client_name}",
                    callback_data=f"mt_export_qr_name:{client_name}",
                )
            ])

        if not keyboard:
            await message.reply_text("❌ У клиентов нет secret для генерации QR")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("Выберите MTProto-клиента для показа QR:", reply_markup=reply_markup)

    async def _reply_tuic_qr(self, message, name: str):
        """Отправить QR и URI для TUIC-клиента."""
        success, response, payload = tuic_manager.build_client_qr_payload(name)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"tuic-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для TUIC-клиента {payload['name']}",
        )
        await message.reply_text(
            "🔷 TUIC QR для клиента {name}\n\n"
            "UUID: {uuid}\n"
            "Password: {password}\n\n"
            "URI:\n{uri}".format(
                name=payload["name"],
                uuid=payload["uuid"],
                password=payload["password"],
                uri=payload["uri"],
            )
        )
        return True

    async def _reply_anytls_qr(self, message, name: str):
        """Отправить QR и URI для AnyTLS-клиента."""
        success, response, payload = anytls_manager.build_client_qr_payload(name)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"anytls-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для AnyTLS-клиента {payload['name']}",
        )
        await message.reply_text(
            "🔶 AnyTLS QR для клиента {name}\n\n"
            "Password: {password}\n\n"
            "URI:\n{uri}".format(
                name=payload["name"],
                password=payload["password"],
                uri=payload["uri"],
            )
        )
        return True

    async def _reply_xhttp_qr(self, message, name: str):
        """Отправить QR и URI для XHTTP-клиента."""
        success, response, payload = xhttp_manager.build_client_qr_payload(name)
        if not success:
            await message.reply_text(response)
            return False

        qr_buffer = payload["qr_buffer"]
        qr_buffer.name = f"xhttp-{payload['name']}.png"

        await message.reply_photo(
            photo=qr_buffer,
            caption=f"QR для XHTTP-клиента {payload['name']}",
        )
        await message.reply_text(
            "🌐 XHTTP QR для клиента {name}\n\n"
            "UUID: {uuid}\n\n"
            "URI:\n{uri}".format(
                name=payload["name"],
                uuid=payload["uuid"],
                uri=payload["uri"],
            )
        )
        return True

    _HELP_MENU_KEYBOARD = [
        [InlineKeyboardButton("🔧 Система", callback_data="help_admin")],
        [
            InlineKeyboardButton("🛡️ VLESS", callback_data="help_vless"),
            InlineKeyboardButton("⚡ Hysteria2", callback_data="help_hy2"),
        ],
        [
            InlineKeyboardButton("🔷 TUIC", callback_data="help_tuic"),
            InlineKeyboardButton("🔶 AnyTLS", callback_data="help_anytls"),
        ],
        [
            InlineKeyboardButton("🌐 XHTTP", callback_data="help_xhttp"),
            InlineKeyboardButton("🌐 NaiveProxy", callback_data="help_naive"),
        ],
        [
            InlineKeyboardButton("📡 MTProto", callback_data="help_mt"),
            InlineKeyboardButton("🧭 TG-Only", callback_data="help_tgcapsule"),
        ],
    ]

    async def _help_show_menu(self, message, *, edit: bool = True):
        """Показать главное меню /help с inline-кнопками.

        Args:
            message: Telegram message object.
            edit: если True — edit_text (для callback), иначе reply_text.
        """
        version_info = get_app_version()
        ver = self._escape_md2(version_info.get("version", "N/A"))
        app_name = self._escape_md2(version_info.get("name", "TelegramOnly"))
        text = (
            f"📚 *{app_name}* v{ver} — выберите раздел:\n\n"
            "/start \\- Запуск бота\n"
            "/help \\- Справка\n"
            "/ver \\- Версия бота\n"
            "/clear \\- Очистить чат"
        )
        reply_markup = InlineKeyboardMarkup(self._HELP_MENU_KEYBOARD)
        if edit:
            await message.edit_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
        else:
            await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)

    # === БАЗОВЫЕ КОМАНДЫ ===

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start - запуск бота и приветствие."""
        try:
            user = update.effective_user
            logger.info(f"User {user.id} ({user.username}) started the bot")
            
            # Проверяем VLESS статус
            vless_status = vless_manager.get_vless_status()
            vless_indicator = "🟢" if vless_status["enabled"] else "🔴"
            
            welcome_message = f"""Привет, {escape_markdown(user.first_name or 'Пользователь')}\\!

🤖 *TelegramOnly* \\- управление API и VLESS\\-Reality

Статус VLESS\\-Reality: {vless_indicator} {"Включён" if vless_status["enabled"] else "Выключен"}

Используйте /help для просмотра команд\\."""
            
            await update.message.reply_text(
                welcome_message,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=ReplyKeyboardRemove()  # Удаляет старые кнопки (RU/EN/FR и др.)
            )
            
        except Exception as e:
            logger.error(f"Error in start_command: {e}")
            await update.message.reply_text(
                "Привет! Используйте /help для просмотра команд."
            )
    
    # === Help: section texts (class-level) ===

    _HELP_SECTIONS = {
        "help_main": (
            "📚 *Основные команды:*\n\n"
            "/start \\- Запуск бота\n"
            "/help \\- Справка \\(это меню\\)\n"
            "/info \\- Информация о пользователе\n"
            "/clear \\- Очистить чат"
        ),
        "help_admin": (
            "🔧 *Система и информация:*\n\n"
            "/info \\- Информация о пользователе\n"
            "/ver \\- Версия\n"
            "/api \\- API ключ \\(маска\\)\n"
            "/gen\\_api\\_key \\- Сгенерировать API ключ\n"
            "/del\\_api\\_key \\- Удалить API ключ\n"
            "/encryption\\_key \\- Ключ шифрования \\(маска\\)\n"
            "/gen\\_encryption\\_key \\- Сгенерировать ключ\n"
            "/del\\_encryption\\_key \\- Удалить ключ\n"
            "/gen\\_chacha\\_key \\- Ключ ChaCha20\n"
            "/gen\\_pqc\\_key \\- Ключ PQC\n\n"
            "*👥 Пользователи:*\n"
            "/list\\_users \\- Список\n"
            "/setcity \\- Город\n"
            "/setgreeting \\- Приветствие\n"
            "/special\\_add \\- Добавить\n"
            "/special\\_remove \\- Удалить\n\n"
            "*🤖 ИИ:*\n"
            "/ai\\_provider \\- Провайдер\n"
            "/ch\\_model \\- Модель"
        ),
        "help_vless": (
            "🛡️ *VLESS\\-Reality:*\n\n"
            "/vless\\_status \\- Статус\n"
            "/vless\\_sync \\- Автонастройка \\+ экспорт\n"
            "/vless\\_config \\- Конфигурация\n"
            "/vless\\_gen\\_keys \\- Сгенерировать ключи\n"
            "/vless\\_reset \\- Сбросить конфиг\n"
            "/vless\\_set\\_port \\- Порт\n"
            "/vless\\_on \\| /vless\\_off \\- Вкл/Выкл\n"
            "/vless\\_test \\- Тест подключения\n"
            "/vless\\_export \\- Экспорт конфигов\n\n"
            "*Клиенты:*\n"
            "/vless\\_add\\_client \\- Добавить\n"
            "/vless\\_del\\_client \\- Удалить\n"
            "/vless\\_list\\_clients \\- Список\n"
            "/vless\\_qr \\- QR клиента\n\n"
            "*Xray сервер:*\n"
            "/xray\\_status \\- Статус Xray\n"
            "/xray\\_config \\- Конфиг сервера"
        ),
        "help_hy2": (
            "⚡ *Hysteria2:*\n\n"
            "/hy2\\_status \\- Статус\n"
            "/hy2\\_config \\- Конфигурация\n"
            "/hy2\\_on \\| /hy2\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/hy2\\_set\\_server \\- IP сервера\n"
            "/hy2\\_set\\_port \\- Порт\n"
            "/hy2\\_set\\_password \\- Пароль\n"
            "/hy2\\_set\\_obfs \\- Обфускация\n"
            "/hy2\\_set\\_speed \\- Скорость\n"
            "/hy2\\_set\\_masquerade \\- Masquerade URL\n\n"
            "*Генерация:*\n"
            "/hy2\\_gen\\_password \\- Пароль\n"
            "/hy2\\_gen\\_cert \\- TLS сертификат\n"
            "/hy2\\_gen\\_all \\- Всё сразу\n\n"
            "*Клиенты:*\n"
            "/hy2\\_add\\_client \\- Добавить\n"
            "/hy2\\_del\\_client \\- Удалить\n"
            "/hy2\\_list\\_clients \\- Список\n"
            "/hy2\\_qr \\- QR клиента\n\n"
            "*Сервис:*\n"
            "/hy2\\_install \\- Установить\n"
            "/hy2\\_apply \\- Применить конфиг\n"
            "/hy2\\_start \\| /hy2\\_stop \\| /hy2\\_restart\n"
            "/hy2\\_logs \\- Логи\n"
            "/hy2\\_export \\- Экспорт"
        ),
        "help_tuic": (
            "🔷 *TUIC:*\n\n"
            "/tuic\\_status \\- Статус\n"
            "/tuic\\_config \\- Конфигурация\n"
            "/tuic\\_on \\| /tuic\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/tuic\\_set\\_server \\- IP сервера\n"
            "/tuic\\_set\\_port \\- Порт\n"
            "/tuic\\_set\\_cc \\- Congestion \\(bbr/cubic\\)\n\n"
            "*Генерация:*\n"
            "/tuic\\_gen\\_cert \\- TLS сертификат\n"
            "/tuic\\_gen\\_all \\- Всё \\(IP\\+cert\\+клиент\\)\n\n"
            "*Клиенты:*\n"
            "/tuic\\_add \\- Добавить\n"
            "/tuic\\_del \\- Удалить\n"
            "/tuic\\_list \\- Список\n"
            "/tuic\\_qr \\- QR клиента\n\n"
            "*Сервис:*\n"
            "/tuic\\_apply \\- Применить конфиг\n"
            "/tuic\\_start \\| /tuic\\_stop \\| /tuic\\_restart\n"
            "/tuic\\_logs \\- Логи\n"
            "/tuic\\_export \\- Экспорт"
        ),
        "help_anytls": (
            "🔶 *AnyTLS:*\n\n"
            "/anytls\\_status \\- Статус\n"
            "/anytls\\_config \\- Конфигурация\n"
            "/anytls\\_on \\| /anytls\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/anytls\\_set\\_server \\- IP сервера\n"
            "/anytls\\_set\\_port \\- Порт\n\n"
            "*Генерация:*\n"
            "/anytls\\_gen\\_cert \\- TLS сертификат\n"
            "/anytls\\_gen\\_all \\- Всё \\(IP\\+cert\\+клиент\\)\n\n"
            "*Клиенты:*\n"
            "/anytls\\_add \\- Добавить\n"
            "/anytls\\_del \\- Удалить\n"
            "/anytls\\_list \\- Список\n"
            "/anytls\\_qr \\- QR клиента\n\n"
            "*Сервис:*\n"
            "/anytls\\_apply \\- Применить конфиг\n"
            "/anytls\\_start \\| /anytls\\_stop \\| /anytls\\_restart\n"
            "/anytls\\_logs \\- Логи\n"
            "/anytls\\_export \\- Экспорт"
        ),
        "help_xhttp": (
            "🌐 *XHTTP \\(VLESS\\+XHTTP\\):*\n\n"
            "/xhttp\\_status \\- Статус\n"
            "/xhttp\\_config \\- Конфигурация\n"
            "/xhttp\\_on \\| /xhttp\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/xhttp\\_set\\_server \\- IP сервера\n"
            "/xhttp\\_set\\_port \\- Порт\n"
            "/xhttp\\_set\\_path \\- Path\n"
            "/xhttp\\_set\\_host \\- Host\n"
            "/xhttp\\_set\\_mode \\- Mode \\(auto/packet\\-up/stream\\-up\\)\n\n"
            "*Генерация:*\n"
            "/xhttp\\_gen\\_cert \\- TLS сертификат\n"
            "/xhttp\\_gen\\_all \\- Всё \\(IP\\+cert\\+клиент\\)\n\n"
            "*Клиенты:*\n"
            "/xhttp\\_add \\- Добавить\n"
            "/xhttp\\_del \\- Удалить\n"
            "/xhttp\\_list \\- Список\n"
            "/xhttp\\_qr \\- QR клиента\n\n"
            "*Сервис:*\n"
            "/xhttp\\_apply \\- Применить конфиг\n"
            "/xhttp\\_start \\| /xhttp\\_stop \\| /xhttp\\_restart\n"
            "/xhttp\\_logs \\- Логи\n"
            "/xhttp\\_export \\- Экспорт"
        ),
        "help_naive": (
            "🌐 *NaiveProxy:*\n\n"
            "/naive\\_status \\- Статус\n"
            "/naive\\_config \\- Конфигурация\n"
            "/naive\\_on \\| /naive\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/naive\\_set\\_domain \\- Домен\n"
            "/naive\\_set\\_port \\- Порт\n"
            "/naive\\_set\\_user \\- Пользователь\n"
            "/naive\\_set\\_password \\- Пароль\n"
            "/naive\\_gen\\_creds \\- Сгенерировать user/password\n\n"
            "*Сервис:*\n"
            "/naive\\_install \\- Установить\n"
            "/naive\\_uri \\- URI клиента\n"
            "/naive\\_apply \\- Caddyfile \\+ перезапуск\n"
            "/naive\\_export \\- Экспорт"
        ),
        "help_mt": (
            "📡 *MTProto Proxy:*\n\n"
            "/mt\\_status \\- Статус\n"
            "/mt\\_config \\- Конфигурация\n"
            "/mt\\_on \\| /mt\\_off \\- Вкл/Выкл\n\n"
            "*Настройки:*\n"
            "/mt\\_set\\_mode \\- Режим dd/ee\n"
            "/mt\\_set\\_server \\- IP сервера\n"
            "/mt\\_set\\_port \\- Порт\n"
            "/mt\\_set\\_domain \\- Fake\\-TLS домен\n"
            "/mt\\_set\\_tag \\- Тег\n"
            "/mt\\_set\\_workers \\- Воркеры\n\n"
            "*Генерация:*\n"
            "/mt\\_gen\\_secret \\- Секрет\n"
            "/mt\\_gen\\_all \\- Всё\n\n"
            "*Клиенты:*\n"
            "/mt\\_add\\_client \\- Добавить\n"
            "/mt\\_del\\_client \\- Удалить\n"
            "/mt\\_list\\_clients \\- Список\n"
            "/mt\\_qr \\- QR клиента\n\n"
            "*Сервис:*\n"
            "/mt\\_install \\- Установить\n"
            "/mt\\_apply \\- Применить конфиг\n"
            "/mt\\_start \\| /mt\\_stop \\| /mt\\_restart\n"
            "/mt\\_logs \\- Логи\n"
            "/mt\\_fetch\\_config \\- Обновить secret\n"
            "/mt\\_export \\- Экспорт"
        ),
        "help_tgcapsule": (
            "🧭 *TelegramOnly Export:*\n\n"
            "/tgcapsule\\_export \\- Профили Telegram\\-only\n"
            "для ApiXgRPC, sing\\-box и Clash Meta\n\n"
            "Используют Reality / Hysteria2 / TUIC /\n"
            "AnyTLS / XHTTP как транспорт,\n"
            "маршрутизируя только Telegram\\-домены\\."
        ),
    }

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help — главное меню справки с inline-кнопками по протоколам."""
        try:
            user = update.effective_user
            logger.info(f"User {user.id} requested help")

            if self._is_admin(user.id):
                await self._help_show_menu(update.message, edit=False)
            else:
                version_info = get_app_version()
                ver = self._escape_md2(version_info.get("version", "N/A"))
                app_name = self._escape_md2(version_info.get("name", "TelegramOnly"))
                text = (
                    f"📚 *{app_name}* v{ver}\n\n"
                    f"*Доступные команды:*\n"
                    "/start \\- Запуск бота\n"
                    "/help \\- Справка\n"
                    "/ver \\- Версия бота\n"
                    "/clear \\- Очистить чат\n\n"
                    "🔒 _Управление протоколами и настройки сервера доступны только администратору\\._"
                )
                await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error(f"Error in help_command: {e}")
            await update.message.reply_text("Ошибка при отображении справки.")
    
    async def info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /info - информация о пользователе (только админ)."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            chat = update.effective_chat
            logger.info(f"Admin {user.id} requested info")

            info_message = format_user_info(user, chat)

            await update.message.reply_text(
                info_message,
                parse_mode=ParseMode.MARKDOWN_V2
            )

        except Exception as e:
            logger.error(f"Error in info_command: {e}")
            await update.message.reply_text(
                "Не удалось получить информацию."
            )
    
    async def clear_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /clear - очистка чата."""
        try:
            user = update.effective_user
            logger.info(f"User {user.id} requested chat clearing")
            
            clear_message = (
                "🧹 *Чат очищен* 🧹\n\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"
                "История сообщений выше этой отметки визуально отделена\\."
            )
            
            await update.message.reply_text(
                clear_message,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
        except Exception as e:
            logger.error(f"Error in clear_chat: {e}")
            await update.message.reply_text("Не удалось очистить чат.")
    
    # === АДМИНСКИЕ КОМАНДЫ - СИСТЕМА И ИНФОРМАЦИЯ ===
    
    async def version_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /ver - информация о версии приложения (доступна всем)."""
        try:
            user = update.effective_user
            logger.info(f"User {user.id} requested version info")

            version_info = get_app_version()

            version_message = f"""📋 *Информация о версии*

🔖 Версия: `{version_info.get('version', 'N/A')}`
📦 Название: {version_info.get('name', 'TelegramOnly')}
📝 Описание: {version_info.get('description', 'N/A')}"""

            # Админ видит расширенную информацию
            if self._is_admin(user.id):
                vless_status = vless_manager.get_vless_status()
                version_message += f"""

🛡️ *VLESS\\-Reality:*
Статус: {"🟢 Включён" if vless_status["enabled"] else "🔴 Выключен"}
Сконфигурирован: {"✅ Да" if vless_status["configured"] else "❌ Нет"}
Сервер: `{vless_status.get("server") or "не настроен"}`"""

            await update.message.reply_text(
                version_message,
                parse_mode=ParseMode.MARKDOWN_V2
            )

        except Exception as e:
            logger.error(f"Error in version_command: {e}")
            await update.message.reply_text("Ошибка при получении информации о версии.")
    
    async def api_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /api - показать маскированный API ключ."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested API key info")
            
            try:
                from security import ALLOWED_APPS
                
                all_apps = ["default"] + list(ALLOWED_APPS.keys())
                
                keyboard = []
                for app_id in all_apps:
                    if app_id == "default":
                        label = "🔑 По умолчанию (из .env)"
                    else:
                        app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                        label = f"🔑 {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"api_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔐 Выберите сервис для просмотра API ключа:",
                    reply_markup=reply_markup
                )
            except ImportError:
                # Если модуль security не найден, показываем дефолтный ключ
                api_key = os.getenv("API_SECRET_KEY", "не настроен")
                masked = self._mask_secret(api_key)
                await update.message.reply_text(f"🔑 API ключ: `{masked}`", parse_mode=ParseMode.MARKDOWN_V2)
                
        except Exception as e:
            logger.error(f"Error in api_command: {e}")
            await update.message.reply_text("Ошибка при получении API ключа.")
    
    async def gen_api_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /gen_api_key - сгенерировать новый API ключ."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to generate new API key")
            
            try:
                from app_keys import list_app_ids
                from security import ALLOWED_APPS
                
                all_apps = ["default"] + list(ALLOWED_APPS.keys())
                
                keyboard = []
                for app_id in all_apps:
                    if app_id == "default":
                        label = "🔑 По умолчанию (в .env)"
                    else:
                        app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                        label = f"🔑 {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"gen_api_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔐 Выберите сервис для генерации нового API ключа:",
                    reply_markup=reply_markup
                )
            except ImportError:
                await update.message.reply_text(
                    "⚠️ Безопасный режим не показывает новый API ключ в Telegram.\n"
                    "Сгенерируйте и сохраните его локально на сервере, затем обновите `API_SECRET_KEY` в `.env`."
                )
                
        except Exception as e:
            logger.error(f"Error in gen_api_key_command: {e}")
            await update.message.reply_text("Ошибка при генерации API ключа.")
    
    async def del_api_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /del_api_key - удалить API ключ."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to delete API key")
            
            try:
                from app_keys import list_app_ids
                from security import ALLOWED_APPS
                
                app_ids = list_app_ids()
                if not app_ids:
                    await update.message.reply_text("❌ Нет сохранённых индивидуальных ключей.")
                    return
                
                keyboard = []
                for app_id in app_ids:
                    app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                    label = f"🗑️ {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"del_api_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🗑️ Выберите сервис для УДАЛЕНИЯ API ключа:",
                    reply_markup=reply_markup
                )
            except ImportError:
                await update.message.reply_text("❌ Модуль app_keys не найден.")
                
        except Exception as e:
            logger.error(f"Error in del_api_key_command: {e}")
            await update.message.reply_text("Ошибка при удалении API ключа.")
    
    async def encryption_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /encryption_key - показать маскированный ключ шифрования."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested Encryption key info")
            
            try:
                from security import ALLOWED_APPS
                
                all_apps = ["default"] + list(ALLOWED_APPS.keys())
                
                keyboard = []
                for app_id in all_apps:
                    if app_id == "default":
                        label = "🔐 По умолчанию (из .env)"
                    else:
                        app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                        label = f"🔐 {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"encryption_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔐 Выберите сервис для просмотра ключа шифрования:",
                    reply_markup=reply_markup
                )
            except ImportError:
                enc_key = os.getenv("ENCRYPTION_KEY", "не настроен")
                masked = self._mask_secret(enc_key)
                await update.message.reply_text(f"🔐 Ключ шифрования: `{masked}`", parse_mode=ParseMode.MARKDOWN_V2)
                
        except Exception as e:
            logger.error(f"Error in encryption_key_command: {e}")
            await update.message.reply_text("Ошибка при получении ключа шифрования.")
    
    async def gen_encryption_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /gen_encryption_key - сгенерировать новый ключ шифрования."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to generate new encryption key")
            
            try:
                from app_keys import list_app_ids
                from security import ALLOWED_APPS
                
                all_apps = ["default"] + list(ALLOWED_APPS.keys())
                
                keyboard = []
                for app_id in all_apps:
                    if app_id == "default":
                        label = "🔐 По умолчанию (в .env)"
                    else:
                        app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                        label = f"🔐 {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"gen_encryption_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🔐 Выберите сервис для генерации нового ключа шифрования:",
                    reply_markup=reply_markup
                )
            except ImportError:
                await update.message.reply_text(
                    "⚠️ Безопасный режим не показывает новый ключ шифрования в Telegram.\n"
                    "Сгенерируйте и сохраните его локально на сервере, затем обновите `ENCRYPTION_KEY` в `.env`."
                )
                
        except Exception as e:
            logger.error(f"Error in gen_encryption_key_command: {e}")
            await update.message.reply_text("Ошибка при генерации ключа шифрования.")
    
    async def del_encryption_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /del_encryption_key - удалить ключ шифрования."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to delete encryption key")
            
            try:
                from app_keys import list_app_ids
                from security import ALLOWED_APPS
                
                app_ids = list_app_ids()
                if not app_ids:
                    await update.message.reply_text("❌ Нет сохранённых индивидуальных ключей.")
                    return
                
                keyboard = []
                for app_id in app_ids:
                    app_name = ALLOWED_APPS.get(app_id, {}).get("name", app_id)
                    label = f"🗑️ {app_name} ({app_id})"
                    keyboard.append([InlineKeyboardButton(label, callback_data=f"del_encryption_key:{app_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    "🗑️ Выберите сервис для УДАЛЕНИЯ ключа шифрования:",
                    reply_markup=reply_markup
                )
            except ImportError:
                await update.message.reply_text("❌ Модуль app_keys не найден.")
                
        except Exception as e:
            logger.error(f"Error in del_encryption_key_command: {e}")
            await update.message.reply_text("Ошибка при удалении ключа шифрования.")
    
    async def gen_chacha_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /gen_chacha_key - сгенерировать ключ ChaCha20-Poly1305."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to generate ChaCha20-Poly1305 key")
            
            key_bytes = secrets.token_bytes(32)
            key_hex = key_bytes.hex()
            key_base64 = base64.b64encode(key_bytes).decode('utf-8')
            
            message = f"""✅ Ключ для ChaCha20-Poly1305 сгенерирован!

🔐 Ключ (hex, 64 символа):
`{key_hex}`

🔐 Ключ (base64):
`{key_base64}`

🔧 Алгоритм: secrets.token_bytes(32) → 256-битный ключ
📊 Размер: 32 байта (256 бит)

💡 ChaCha20-Poly1305:
• Современная альтернатива AES-256-GCM
• Отличная производительность на ARM/мобильных
• Используется в WireGuard, Signal, TLS 1.3

⚠️ Это тестовая команда"""
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in gen_chacha_key_command: {e}")
            await update.message.reply_text("Ошибка при генерации ключа ChaCha20-Poly1305.")
    
    async def gen_pqc_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /gen_pqc_key - сгенерировать ключ для Post-Quantum Cryptography."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested to generate PQC key")
            
            key_bytes = secrets.token_bytes(48)
            key_hex = key_bytes.hex()
            key_base64 = base64.b64encode(key_bytes).decode('utf-8')
            
            message = f"""✅ Ключ для Post-Quantum Cryptography сгенерирован!

🔐 Ключ (hex, 96 символов):
`{key_hex}`

🔐 Ключ (base64):
`{key_base64}`

🔧 Размер: 48 байт (384 бит) - для CRYSTALS-Kyber-768
🛡️ Уровень безопасности: NIST Level 3

💡 Post-Quantum Cryptography (PQC):
• Защита от квантовых компьютеров
• CRYSTALS-Kyber - стандарт NIST

⚠️ Это тестовая команда"""
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in gen_pqc_key_command: {e}")
            await update.message.reply_text("Ошибка при генерации PQC ключа.")
    
    # === УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ===
    
    async def admin_setcity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /setcity - установить город для пользователя."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text("Использование: /setcity <user_id> <city>")
            return
        
        try:
            target_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return
        
        city = " ".join(args[1:]).strip()
        if not city:
            await update.message.reply_text("Город не может быть пустым")
            return
        
        set_user_city(target_id, city)
        await update.message.reply_text(f"✅ Город установлен для {target_id}: {city}")
    
    async def admin_setgreeting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /setgreeting - установить приветствие для пользователя."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text("Использование: /setgreeting <user_id> <text>")
            return
        
        try:
            target_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return
        
        greeting = " ".join(args[1:]).strip()
        if not greeting:
            await update.message.reply_text("Приветствие не может быть пустым")
            return
        
        set_user_greeting(target_id, greeting)
        await update.message.reply_text(f"✅ Приветствие установлено для {target_id}")
    
    async def admin_special_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /special_add - добавить особого пользователя."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        args = context.args or []
        if len(args) != 1:
            await update.message.reply_text("Использование: /special_add <user_id>")
            return
        
        try:
            target_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return
        
        add_special_user(target_id)
        await update.message.reply_text(f"✅ Пользователь {target_id} добавлен в особые")
    
    async def admin_special_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /special_remove - удалить особого пользователя."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        args = context.args or []
        if len(args) != 1:
            await update.message.reply_text("Использование: /special_remove <user_id>")
            return
        
        try:
            target_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Неверный user_id")
            return
        
        remove_special_user(target_id)
        await update.message.reply_text(f"✅ Пользователь {target_id} удалён из особых")
    
    async def admin_list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /list_users - список пользователей."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        special, users = storage_list_users()
        lines = ["*Особые пользователи:*"]
        lines.append(", ".join([str(x) for x in special]) if special else "\\-")
        lines.append("\n*Пользователи:*")
        if users:
            for uid, prefs in users.items():
                city = escape_markdown(prefs.get("city", "-"))
                lines.append(f"`{uid}`: city\\={city}")
        else:
            lines.append("\\-")
        
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
    
    # === НАСТРОЙКИ ИИ ===
    
    async def ai_set_provider(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /ai_provider - выбрать провайдера ИИ."""
        user = update.effective_user
        if not self._is_admin(user.id):
            await update.message.reply_text("⛔ Эта команда доступна только администратору.")
            return
        
        args = context.args or []
        if len(args) != 1 or args[0].lower() not in ["openai", "anthropic"]:
            await update.message.reply_text("Использование: /ai_provider <openai|anthropic>")
            return
        
        provider = args[0].lower()
        os.environ["DEFAULT_AI_PROVIDER"] = provider
        
        emoji = "🔵" if provider == "openai" else "🟣"
        await update.message.reply_text(f"{emoji} Провайдер ИИ установлен: {provider}")
    
    async def ch_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /ch_model - переключить AI модель."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            keyboard = [
                [
                    InlineKeyboardButton("OpenAI (GPT)", callback_data="model_select_openai"),
                    InlineKeyboardButton("Anthropic (Claude)", callback_data="model_select_anthropic")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚙️ Выберите провайдера для настройки модели:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in ch_model_command: {e}")
            await update.message.reply_text("Ошибка при выполнении команды.")
    
    # === КОМАНДЫ VLESS-REALITY ===
    
    async def vless_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_status - показать статус VLESS-Reality."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested VLESS status")
            
            status = vless_manager.get_vless_status()
            
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"
            
            # Экранируем спецсимволы для Markdown V2
            def escape_md2(text):
                if not text:
                    return "не настроен"
                text = str(text)
                for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
                    text = text.replace(char, f'\\{char}')
                return text
            
            server = escape_md2(status.get("server"))
            port = escape_md2(status.get("port", 443))
            sni = escape_md2(status.get("sni", "www.microsoft.com"))
            fingerprint = escape_md2(status.get("fingerprint", "chrome"))
            updated_at = escape_md2(status.get("updated_at", "никогда"))
            
            message = f"""🛡️ *VLESS\\-Reality Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{server}`
• Порт: `{port}`
• SNI: `{sni}`
• Fingerprint: `{fingerprint}`

*Ключи:*
• UUID: {"✅" if status["has_uuid"] else "❌"}
• Public Key: {"✅" if status["has_public_key"] else "❌"}
• Private Key: {"✅" if status["has_private_key"] else "❌"}
• Short ID: {"✅" if status["has_short_id"] else "❌"}

_Обновлено: {updated_at}_"""
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in vless_status: {e}")
            await update.message.reply_text("Ошибка при получении статуса VLESS.")
    
    async def vless_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_on - включить VLESS-Reality."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} enabling VLESS-Reality")
            
            success, message = vless_manager.enable_vless()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_on: {e}")
            await update.message.reply_text("Ошибка при включении VLESS.")
    
    async def vless_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_off - выключить VLESS-Reality."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} disabling VLESS-Reality")
            
            success, message = vless_manager.disable_vless()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_off: {e}")
            await update.message.reply_text("Ошибка при выключении VLESS.")
    
    async def vless_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_config - показать и сохранить конфигурацию VLESS в файлы."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} requested VLESS config")
            
            config = vless_manager.get_vless_config(include_secrets=False)
            
            # Сохраняем конфиги в файлы
            success, save_msg, created_files = vless_manager.save_vless_config_files()
            
            # Формируем список сохранённых файлов
            files_list = ""
            if created_files:
                files_list = "\n\n📁 *Сохранённые файлы:*\n"
                for f in created_files:
                    # Показываем только имя файла без полного пути
                    fname = os.path.basename(f)
                    files_list += f"• `{fname}`\n"
            
            # Escape для Markdown V2
            save_msg_escaped = escape_markdown(save_msg)
            
            message = f"""🔧 *Конфигурация VLESS\\-Reality*

```json
{json.dumps(config, indent=2, ensure_ascii=False)}
```

{save_msg_escaped}{files_list}
💡 Секретные данные скрыты\\. Для полной конфигурации используйте /vless\\_export"""
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in vless_config: {e}")
            await update.message.reply_text("Ошибка при получении конфигурации VLESS.")
    
    async def vless_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_server - установить адрес сервера (автоопределение если без аргументов)."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            
            # Если аргумент указан - используем его, иначе автоопределение
            if len(args) >= 1:
                server = args[0]
            else:
                await update.message.reply_text("🔍 Определяю IP сервера...")
                server = None  # Автоопределение
            
            success, message = vless_manager.set_vless_server(server)
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_server: {e}")
            await update.message.reply_text("Ошибка при установке сервера.")
    
    async def vless_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_port - установить порт."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_set_port <port>")
                return
            
            try:
                port = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Порт должен быть числом")
                return
            
            success, message = vless_manager.set_vless_port(port)
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_port: {e}")
            await update.message.reply_text("Ошибка при установке порта.")
    
    async def vless_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_add_client - добавить клиента VLESS."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            args = context.args or []
            if len(args) < 1:
                await update.message.reply_text("Использование: /vless_add_client <name> [uuid]")
                return

            name = args[0]
            client_uuid = args[1] if len(args) > 1 else None

            success, message, client = vless_manager.add_client(name, client_uuid)
            if success:
                uuid_display = client.get("uuid", "")
                response = f"{message}\nUUID: `{uuid_display}`"
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)
                await self._reply_vless_qr(update.message, client.get("uuid", name))
                # Автоматически применяем конфиг к Xray
                apply_ok, apply_msg = vless_manager.apply_xray_config()
                await update.message.reply_text(apply_msg)
            else:
                await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Error in vless_add_client: {e}")
            await update.message.reply_text("Ошибка при добавлении клиента.")

    async def vless_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_qr - показать QR для VLESS-клиента."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ QR-коды VLESS доступны только администратору.")
                return

            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_qr <client_name_or_uuid>")
                return

            await self._reply_vless_qr(update.message, args[0])

        except Exception as e:
            logger.error(f"Error in vless_qr: {e}")
            await update.message.reply_text("Ошибка при показе QR клиента.")

    async def vless_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_list_clients - список клиентов VLESS."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            clients = vless_manager.list_clients()
            if not clients:
                await update.message.reply_text("Список клиентов пуст.")
                return

            lines = ["*VLESS клиенты:*"]
            for client in clients:
                name = escape_markdown(str(client.get("name", "client")))
                uuid = escape_markdown(str(client.get("uuid", "")))
                lines.append(f"• {name}: `{uuid}`")

            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error(f"Error in vless_list_clients: {e}")
            await update.message.reply_text("Ошибка при получении списка клиентов.")

    async def vless_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_del_client - удалить клиента VLESS."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_del_client <name_or_uuid>")
                return

            success, message = vless_manager.remove_client(args[0])
            await update.message.reply_text(message)

        except Exception as e:
            logger.error(f"Error in vless_del_client: {e}")
            await update.message.reply_text("Ошибка при удалении клиента.")

    async def vless_set_uuid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_uuid - установить UUID."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_set_uuid <uuid>")
                return
            
            success, message = vless_manager.set_vless_uuid(args[0])
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_uuid: {e}")
            await update.message.reply_text("Ошибка при установке UUID.")
    
    async def vless_set_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_key - установить публичный ключ Reality."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_set_key <public_key>")
                return
            
            success, message = vless_manager.set_vless_public_key(args[0])
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_key: {e}")
            await update.message.reply_text("Ошибка при установке ключа.")
    
    async def vless_set_shortid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_shortid - установить Short ID."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /vless_set_shortid <hex_string>")
                return
            
            success, message = vless_manager.set_vless_short_id(args[0])
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_shortid: {e}")
            await update.message.reply_text("Ошибка при установке Short ID.")
    
    async def vless_set_sni(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_sni - установить SNI для маскировки."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                sni_list = ", ".join(vless_manager.AVAILABLE_SNI[:4])
                await update.message.reply_text(
                    f"Использование: /vless_set_sni <domain>\n\nРекомендуемые: {sni_list}"
                )
                return
            
            success, message = vless_manager.set_vless_sni(args[0])
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_sni: {e}")
            await update.message.reply_text("Ошибка при установке SNI.")
    
    async def vless_set_fingerprint(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_set_fingerprint - установить TLS fingerprint."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            args = context.args or []
            if len(args) != 1:
                fp_list = ", ".join(vless_manager.AVAILABLE_FINGERPRINTS)
                await update.message.reply_text(
                    f"Использование: /vless_set_fingerprint <fingerprint>\n\nДоступные: {fp_list}"
                )
                return
            
            success, message = vless_manager.set_vless_fingerprint(args[0])
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_set_fingerprint: {e}")
            await update.message.reply_text("Ошибка при установке fingerprint.")
    
    async def vless_gen_keys(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_gen_keys - сгенерировать все ключи VLESS-Reality."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} generating VLESS keys")
            
            await update.message.reply_text("⏳ Генерация ключей...")
            
            success, keys, message = vless_manager.generate_all_keys()
            
            if success:
                response = f"""{message}

🔑 *Сгенерированные ключи:*

*UUID:*
`{keys.get("uuid", "")}`

*Public Key:*
`{keys.get("public_key", "")}`

*Short ID:*
`{keys.get("short_id", "")}`

⚠️ *Важно:*
• Private Key сохранён только на сервере и не отправляется в Telegram
• Public Key и Short ID нужны для клиента
• UUID должен совпадать на сервере и клиенте"""
                
                await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_gen_keys: {e}")
            await update.message.reply_text("Ошибка при генерации ключей.")
    
    async def vless_test(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_test - тест подключения к серверу."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} testing VLESS connection")
            
            await update.message.reply_text("⏳ Тестирование подключения...")
            
            success, message = vless_manager.test_connection()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in vless_test: {e}")
            await update.message.reply_text("Ошибка при тестировании подключения.")
    
    async def vless_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_export - экспорт конфигурации."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} exporting VLESS config")
            
            # Клиентская конфигурация
            client_config = vless_manager.export_client_config()
            
            # Xray конфигурации
            xray_client = vless_manager.export_xray_config(is_server=False)
            xray_server = vless_manager.export_xray_config(is_server=True)
            
            # Generate VLESS link
            vless_link = vless_manager.generate_vless_link()
            vless_link_escaped = escape_markdown(vless_link)
            
            message = f"""📤 *Экспорт конфигурации VLESS\\-Reality*

*Конфигурация клиента:*
```json
{json.dumps(client_config, indent=2)}
```

🔗 *Ссылка для Hiddify / Foxray / v2rayNG:*
`{vless_link_escaped}`

Для полной конфигурации Xray используйте команды ниже\\."""
            
            keyboard = [
                [InlineKeyboardButton("📱 Xray Client Config", callback_data="vless_export_client")],
                [InlineKeyboardButton("🖥️ Xray Server Config", callback_data="vless_export_server")],
                [InlineKeyboardButton("📷 QR по клиенту", callback_data="vless_export_qr_menu")],
                [InlineKeyboardButton("📦 Subscription (base64)", callback_data="vless_export_sub_base64")],
                [InlineKeyboardButton("📄 Subscription (raw)", callback_data="vless_export_sub_raw")],
                [InlineKeyboardButton("🧩 Sing-box Config", callback_data="vless_export_singbox")],
                [InlineKeyboardButton("🧩 Clash Meta Config", callback_data="vless_export_clash")],
                [InlineKeyboardButton("📲 ApiXgRPC Profile", callback_data="vless_export_apisb")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in vless_export: {e}")
            await update.message.reply_text("Ошибка при экспорте конфигурации.")
    
    async def vless_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_sync - автонастройка и экспорт для клиента ApiXgRPC."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} syncing VLESS config for client")
            
            # Сначала синхронизируем ключи из xray config (если xray установлен и работает)
            # Это гарантирует что public_key в vless_config.json соответствует privateKey в xray
            sync_success, sync_msg = vless_manager.sync_from_xray_config()
            if sync_success and "Синхронизировано" in sync_msg:
                await update.message.reply_text("🔄 " + sync_msg.replace("`", ""), parse_mode=None)
            
            # Получаем текущую конфигурацию
            config = vless_manager.get_vless_config(include_secrets=True)
            
            auto_configured = False
            
            # Если сервер не настроен - автоопределение
            if not config.get("server") or "..." in str(config.get("server", "")):
                await update.message.reply_text("🔍 Определяю IP сервера...")
                success, msg = vless_manager.set_vless_server(None)  # Автоопределение
                if not success:
                    await update.message.reply_text(msg)
                    return
                await update.message.reply_text(msg)
                auto_configured = True
                config = vless_manager.get_vless_config(include_secrets=True)
            
            # Если ключи не сгенерированы - генерируем
            if not config.get("uuid") or "..." in str(config.get("uuid", "")):
                await update.message.reply_text("🔑 Генерирую ключи...")
                success, keys, msg = vless_manager.generate_all_keys()
                if not success:
                    await update.message.reply_text(msg)
                    return
                await update.message.reply_text(msg)
                auto_configured = True
                config = vless_manager.get_vless_config(include_secrets=True)
            
            # Получаем полную конфигурацию для экспорта
            full_config = vless_manager.export_client_config()
            
            # Escaping для Markdown
            server_escaped = escape_markdown(full_config["server"])
            uuid_escaped = escape_markdown(full_config["uuid"])
            pk_escaped = escape_markdown(full_config["public_key"])
            sid_escaped = escape_markdown(full_config["short_id"])
            
            if auto_configured:
                header = "✅ *VLESS\\-Reality настроен автоматически\\!*"
            else:
                header = "🔄 *VLESS\\-Reality для ApiXgRPC*"
            
            # Generate VLESS link
            vless_link = vless_manager.generate_vless_link()
            vless_link_escaped = escape_markdown(vless_link)

            message = f"""{header}

*Скопируйте эти значения в Settings → Reality:*

📍 *Server:* `{server_escaped}`
🔌 *Port:* `{full_config["port"]}`
🆔 *UUID:* `{uuid_escaped}`
🔑 *Public Key:* `{pk_escaped}`
🏷️ *Short ID:* `{sid_escaped}`
🌐 *SNI:* `{full_config["sni"]}`
🎭 *Fingerprint:* `{full_config["fingerprint"]}`

🔗 *Ссылка для Hiddify / Foxray / v2rayNG:*
`{vless_link_escaped}`

💡 _Откройте ApiXgRPC → Settings → VLESS\\-Reality → Configure Reality_"""
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in vless_sync: {e}")
            await update.message.reply_text("Ошибка при синхронизации конфигурации.")
    
    async def vless_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /vless_reset - сбросить конфигурацию VLESS."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} resetting VLESS config")
            
            # Запрашиваем подтверждение
            keyboard = [
                [
                    InlineKeyboardButton("✅ Да, сбросить", callback_data="vless_reset_confirm"),
                    InlineKeyboardButton("❌ Отмена", callback_data="vless_reset_cancel")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ *Вы уверены, что хотите сбросить конфигурацию VLESS\\-Reality?*\n\n"
                "Все настройки и ключи будут удалены\\!",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in vless_reset: {e}")
            await update.message.reply_text("Ошибка при сбросе конфигурации.")
    
    # === XRAY MANAGEMENT COMMANDS ===
    
    async def xray_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_status - проверить статус Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} checking Xray status")
            
            installed, message, info = vless_manager.check_xray_installed()
            
            if not installed:
                message += "\n\n💡 Для установки: /xray\\_install"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in xray_status: {e}")
            await update.message.reply_text("Ошибка при проверке статуса Xray.")
    
    async def xray_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_config - показать конфигурацию Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} viewing Xray config")
            
            success, message, config = vless_manager.get_xray_config()
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in xray_config: {e}")
            await update.message.reply_text("Ошибка при получении конфигурации Xray.")
    
    async def xray_install(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_install - установить Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} installing Xray")
            
            await update.message.reply_text("⏳ Устанавливаю Xray... (может занять 1-2 минуты)")
            
            success, message = vless_manager.install_xray()
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in xray_install: {e}")
            await update.message.reply_text("Ошибка при установке Xray.")
    
    async def xray_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_apply - применить VLESS конфигурацию к Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} applying Xray config")
            
            success, message = vless_manager.apply_xray_config()
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in xray_apply: {e}")
            await update.message.reply_text("Ошибка при применении конфигурации.")
    
    async def xray_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_start - запустить Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} starting Xray")
            
            success, message = vless_manager.start_xray()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in xray_start: {e}")
            await update.message.reply_text("Ошибка при запуске Xray.")
    
    async def xray_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_stop - остановить Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} stopping Xray")
            
            success, message = vless_manager.stop_xray()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in xray_stop: {e}")
            await update.message.reply_text("Ошибка при остановке Xray.")
    
    async def xray_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_restart - перезапустить Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} restarting Xray")
            
            await update.message.reply_text("⏳ Перезапускаю Xray...")
            
            success, message = vless_manager.restart_xray()
            await update.message.reply_text(message)
            
        except Exception as e:
            logger.error(f"Error in xray_restart: {e}")
            await update.message.reply_text("Ошибка при перезапуске Xray.")
    
    async def xray_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xray_logs - показать логи Xray."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            
            logger.info(f"Admin {user.id} viewing Xray logs")
            
            # Парсим количество строк из аргументов
            args = context.args or []
            lines = 30
            if args and args[0].isdigit():
                lines = min(int(args[0]), 100)  # Максимум 100 строк
            
            success, message = vless_manager.get_xray_logs(lines)
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            
        except Exception as e:
            logger.error(f"Error in xray_logs: {e}")
            await update.message.reply_text("Ошибка при получении логов.")
    
    # === NGINX SNI ROUTING COMMANDS ===

    async def nginx_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /nginx_status - статус Nginx SNI fallback."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            config = vless_manager._load_config()
            enabled = config.get("nginx_fallback_enabled", False)
            port = config.get("nginx_fallback_port", 8443)
            hs_domain = config.get("headscale_domain", "")
            ha_domain = config.get("ha_domain", "")

            status_emoji = "🟢" if enabled else "🔴"
            lines = [
                f"{status_emoji} *Nginx SNI Fallback*: {'включён' if enabled else 'выключен'}",
                f"📍 *Порт*: `{port}`",
                f"🌐 *Headscale домен*: `{escape_markdown(hs_domain or 'не задан')}`",
            ]
            if ha_domain:
                lines.append(f"🏠 *Home Assistant домен*: `{escape_markdown(ha_domain)}`")

            await update.message.reply_text(
                "\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Error in nginx_status: {e}")
            await update.message.reply_text("Ошибка при получении статуса Nginx.")

    async def nginx_enable(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /nginx_enable - включить Nginx SNI fallback."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            args = context.args or []
            port = int(args[0]) if args and args[0].isdigit() else 8443
            success, message = vless_manager.set_nginx_fallback(True, port)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in nginx_enable: {e}")
            await update.message.reply_text("Ошибка при включении Nginx fallback.")

    async def nginx_disable(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /nginx_disable - выключить Nginx SNI fallback."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            success, message = vless_manager.set_nginx_fallback(False)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in nginx_disable: {e}")
            await update.message.reply_text("Ошибка при выключении Nginx fallback.")

    async def nginx_set_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /nginx_set_domain <headscale_domain> [ha_domain]."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            args = context.args or []
            if not args:
                await update.message.reply_text(
                    "Использование: /nginx_set_domain <headscale_domain> [ha_domain]\n"
                    "Пример: /nginx_set_domain headscale.example.com ha.example.com"
                )
                return

            headscale_domain = args[0]
            ha_domain = args[1] if len(args) > 1 else ""
            success, message = vless_manager.set_nginx_domains(headscale_domain, ha_domain)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in nginx_set_domain: {e}")
            await update.message.reply_text("Ошибка при установке домена.")

    async def nginx_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /nginx_config - вывести Nginx конфиг для копирования на VPS."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            success, config_text = vless_manager.get_nginx_sni_config()
            if success:
                await update.message.reply_text(
                    f"```nginx\n{config_text}\n```",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await update.message.reply_text(config_text)
        except Exception as e:
            logger.error(f"Error in nginx_config: {e}")
            await update.message.reply_text("Ошибка при генерации конфига Nginx.")

    # === HEADSCALE COMMANDS ===

    async def headscale_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_status - статус Headscale."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            status = headscale_manager.get_status()
            enabled_emoji = "🟢" if status["enabled"] else "🔴"
            container_emoji = "🟢" if status["container_running"] else "🔴"

            lines = [
                f"{enabled_emoji} *Headscale*: {'включён' if status['enabled'] else 'выключен'}",
                f"{container_emoji} *Контейнер* `{escape_markdown(status['container_name'])}`: "
                f"{'запущен' if status['container_running'] else 'остановлен'}",
                f"🌐 *URL*: `{escape_markdown(status['server_url'] or 'не задан')}`",
                f"💻 *Ноды*: {status['node_count']}",
                f"👤 *Пользователи*: {status['user_count']}",
            ]
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in headscale_status: {e}")
            await update.message.reply_text("Ошибка при получении статуса Headscale.")

    async def headscale_enable(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_enable."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            success, message = headscale_manager.enable_headscale()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in headscale_enable: {e}")
            await update.message.reply_text("Ошибка.")

    async def headscale_disable(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_disable."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            success, message = headscale_manager.disable_headscale()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in headscale_disable: {e}")
            await update.message.reply_text("Ошибка.")

    async def headscale_set_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_set_url <url>."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text(
                    "Использование: /headscale_set_url https://headscale.example.com"
                )
                return
            success, message = headscale_manager.set_server_url(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in headscale_set_url: {e}")
            await update.message.reply_text("Ошибка.")

    async def headscale_gen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_gen - генерация Pre-Auth ключа."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            args = context.args or []
            hs_user = args[0] if args else None

            success, message, key = headscale_manager.create_preauth_key(user=hs_user)
            if success and key:
                instructions = headscale_manager.export_client_instructions(key)
                await update.message.reply_text(f"{message}\n\n```\n{instructions}\n```",
                                                parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in headscale_gen: {e}")
            await update.message.reply_text("Ошибка при генерации ключа.")

    async def headscale_list_nodes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_list_nodes - список нод."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            success, message, nodes = headscale_manager.list_nodes()
            if not success:
                await update.message.reply_text(message)
                return

            if not nodes:
                await update.message.reply_text("📋 Подключённых нод нет.")
                return

            lines = [f"📋 *Ноды Headscale* \\({len(nodes)}\\):"]
            for node in nodes[:20]:  # Limit to 20
                name = escape_markdown(node.get("givenName", node.get("name", "?")))
                ip = node.get("ipAddresses", ["?"])[0] if node.get("ipAddresses") else "?"
                online = "🟢" if node.get("online", False) else "🔴"
                lines.append(f"  {online} `{name}` — `{escape_markdown(ip)}`")

            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in headscale_list_nodes: {e}")
            await update.message.reply_text("Ошибка при получении списка нод.")

    async def headscale_create_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /headscale_create_user <name>."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /headscale_create_user <username>")
                return
            success, message = headscale_manager.create_user(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in headscale_create_user: {e}")
            await update.message.reply_text("Ошибка при создании пользователя.")

    # === CALLBACK QUERY HANDLER ===

    async def callback_query_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback queries от inline клавиатур."""
        query = update.callback_query
        await query.answer()

        data = query.data

        # Все callback queries доступны только администраторам
        if not self._is_admin(query.from_user.id):
            await query.message.reply_text("⛔ Только для администратора.")
            return

        # === Help section callbacks ===
        if data.startswith("help_"):
            try:
                if data == "help_back":
                    await self._help_show_menu(query.message)
                    return
                section_text = self._HELP_SECTIONS.get(data)
                if section_text:
                    back_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Назад к меню", callback_data="help_back")]
                    ])
                    await query.message.edit_text(
                        section_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=back_kb,
                    )
                    return
            except Exception as e:
                logger.error(f"Error in help callback '{data}': {e}")
                # Fallback: отправить новым сообщением без MarkdownV2
                section_text = self._HELP_SECTIONS.get(data, "")
                if section_text:
                    plain = section_text.replace("\\", "").replace("*", "").replace("`", "")
                    back_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Назад к меню", callback_data="help_back")]
                    ])
                    await query.message.reply_text(plain, reply_markup=back_kb)
                return
                return

        # === API Key callbacks ===
        if data.startswith("api_key:"):
            app_id = data.split(":", 1)[1]
            await self._show_api_key(update, app_id)
            return
        
        if data.startswith("show_full_api_key:"):
            app_id = data.split(":", 1)[1]
            await self._show_full_api_key(update, app_id)
            return
        
        if data.startswith("encryption_key:"):
            app_id = data.split(":", 1)[1]
            await self._show_encryption_key(update, app_id)
            return
        
        if data.startswith("show_full_enc_key:"):
            app_id = data.split(":", 1)[1]
            await self._show_full_encryption_key(update, app_id)
            return
        
        if data.startswith("gen_api_key:"):
            app_id = data.split(":", 1)[1]
            await self._generate_api_key(update, app_id)
            return
        
        if data.startswith("gen_encryption_key:"):
            app_id = data.split(":", 1)[1]
            await self._generate_encryption_key(update, app_id)
            return
        
        if data.startswith("del_api_key:"):
            app_id = data.split(":", 1)[1]
            await self._delete_api_key(update, app_id)
            return
        
        if data.startswith("del_encryption_key:"):
            app_id = data.split(":", 1)[1]
            await self._delete_encryption_key(update, app_id)
            return
        
        # === Model selection callbacks ===
        if data.startswith("model_select_"):
            provider = data.replace("model_select_", "")
            await self._show_model_selection(update, context, provider)
            return
        
        if data.startswith("model_set_"):
            parts = data.replace("model_set_", "").split("_", 1)
            if len(parts) == 2:
                provider, model = parts
                if set_current_model(provider, model):
                    await query.message.edit_text(f"✅ Модель для {provider.upper()} изменена на {model}")
                else:
                    await query.message.edit_text(f"❌ Ошибка при установке модели {model}")
            return
        
        # === VLESS callbacks ===
        if data == "vless_export_client":
            xray_config = vless_manager.export_xray_config(is_server=False)
            await query.message.reply_text(
                f"📱 *Xray Client Config:*\n```json\n{json.dumps(xray_config, indent=2)}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        if data == "vless_export_server":
            xray_config = vless_manager.export_xray_config(is_server=True)
            config_json = json.dumps(xray_config, indent=2)
            
            # Выводим конфиг
            await query.message.reply_text(
                f"🖥️ *Xray Server Config:*\n```json\n{config_json}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            # Выводим инструкцию
            instructions = """💡 *Как применить на сервере \\(SSH\\):*

*1\\. Подключитесь к серверу:*
```
ssh root@<IP\\_СЕРВЕРА>
```

*2\\. Откройте редактор nano:*
```
nano /usr/local/etc/xray/config\\.json
```

*3\\. В nano:*
• Удалите всё: зажмите `Ctrl\\+K` несколько раз
• Вставьте JSON: `Ctrl\\+Shift\\+V` \\(или ПКМ → Вставить\\)
• Сохраните: `Ctrl\\+O`, затем `Enter`
• Выйдите: `Ctrl\\+X`

*4\\. Проверьте и запустите:*
```
xray \\-test \\-config /usr/local/etc/xray/config\\.json
systemctl restart xray
systemctl status xray
```

✅ Если видите `Active: active \\(running\\)` \\- готово\\!"""
            await query.message.reply_text(instructions, parse_mode=ParseMode.MARKDOWN_V2)
            return

        if data == "vless_export_qr_menu":
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды VLESS доступны только администратору.")
                return
            await self._show_vless_qr_selection(query.message)
            return

        if data.startswith("vless_export_qr_uuid:"):
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды VLESS доступны только администратору.")
                return
            client_uuid = data.split(":", 1)[1]
            await self._reply_vless_qr(query.message, client_uuid)
            return

        if data == "vless_export_sub_base64":
            sub_base64 = vless_manager.export_subscription_base64()
            if not sub_base64:
                await query.message.reply_text("❌ Нет данных для subscription. Проверьте /vless_sync")
                return
            await self._reply_export_file(
                query.message,
                sub_base64,
                "vless-subscription-base64.txt",
                "📦 Subscription (base64)"
            )
            return

        if data == "vless_export_sub_raw":
            links = vless_manager.export_subscription_list()
            if not links:
                await query.message.reply_text("❌ Нет данных для subscription. Проверьте /vless_sync")
                return
            raw_list = "\n".join(links)
            await self._reply_export_file(
                query.message,
                raw_list,
                "vless-subscription-raw.txt",
                "📄 Subscription (raw)"
            )
            return

        if data == "vless_export_singbox":
            singbox_config = vless_manager.export_singbox_config()
            await self._reply_export_file(
                query.message,
                json.dumps(singbox_config, indent=2, ensure_ascii=False),
                "vless-singbox-config.json",
                "🧩 Sing-box Config"
            )
            return

        if data == "vless_export_clash":
            clash_config = vless_manager.export_clash_meta_config()
            await query.message.reply_text(
                f"🧩 *Clash Meta Config:*\n```yaml\n{clash_config}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "vless_export_apisb":
            apisb = vless_manager.export_apisb_profile()
            await query.message.reply_text(
                f"📲 *ApiXgRPC Profile \\(Reality\\):*\n```json\n{json.dumps(apisb, indent=2)}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # === Hysteria2 export callbacks ===
        if data == "hy2_export_apisb":
            apisb = hysteria2_manager.export_apisb_profile()
            await query.message.reply_text(
                f"📲 *ApiXgRPC Profile \\(Hysteria2\\):*\n```json\n{json.dumps(apisb, indent=2)}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "hy2_export_singbox":
            singbox_config = hysteria2_manager.export_singbox_config()
            await query.message.reply_text(
                f"🧩 *Sing\\-box Config \\(Hysteria2\\):*\n```json\n{json.dumps(singbox_config, indent=2)}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "hy2_export_clash":
            clash_config = hysteria2_manager.export_clash_meta_config()
            await query.message.reply_text(
                f"🧩 *Clash Meta Config \\(Hysteria2\\):*\n```yaml\n{clash_config}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "hy2_export_server":
            server_yaml = hysteria2_manager.export_server_config_yaml()
            await query.message.reply_text(
                f"🖥️ *Server Config \\(Hysteria2\\):*\n```yaml\n{server_yaml}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "hy2_export_sub_base64":
            sub = hysteria2_manager.export_subscription_base64()
            if sub:
                await self._reply_export_file(
                    query.message,
                    sub,
                    "hy2-subscription-base64.txt",
                    "📦 Subscription (base64)"
                )
            else:
                await query.message.reply_text("❌ Нет данных для subscription")
            return

        if data == "hy2_export_qr_menu":
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды Hysteria2 доступны только администратору.")
                return
            await self._show_hy2_qr_selection(query.message)
            return

        if data.startswith("hy2_export_qr_pw:"):
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды Hysteria2 доступны только администратору.")
                return
            client_password = data.split(":", 1)[1]
            await self._reply_hy2_qr(query.message, client_password)
            return

        # === TelegramOnly export callbacks ===
        if data == "tgc_export_apix_reality":
            profile = telegram_capsule_export.export_apix_profile_v2("reality")
            await self._reply_export_file(
                query.message,
                json.dumps(profile, indent=2, ensure_ascii=False),
                "telegramonly-reality.apix.json",
                "TelegramOnly ApiXgRPC profile (Reality)"
            )
            return

        if data == "tgc_export_apix_hy2":
            profile = telegram_capsule_export.export_apix_profile_v2("hysteria2")
            await self._reply_export_file(
                query.message,
                json.dumps(profile, indent=2, ensure_ascii=False),
                "telegramonly-hysteria2.apix.json",
                "TelegramOnly ApiXgRPC profile (Hysteria2)"
            )
            return

        if data == "tgc_export_apix_auto":
            profile = telegram_capsule_export.export_apix_profile_v2("auto")
            await self._reply_export_file(
                query.message,
                json.dumps(profile, indent=2, ensure_ascii=False),
                "telegramonly-auto.apix.json",
                "TelegramOnly ApiXgRPC profile (Auto)"
            )
            return

        if data == "tgc_export_sb_reality":
            config = telegram_capsule_export.export_singbox_config("reality")
            await self._reply_export_file(
                query.message,
                json.dumps(config, indent=2, ensure_ascii=False),
                "telegramonly-reality-singbox.json",
                "TelegramOnly sing-box config (Reality)"
            )
            return

        if data == "tgc_export_sb_hy2":
            config = telegram_capsule_export.export_singbox_config("hysteria2")
            await self._reply_export_file(
                query.message,
                json.dumps(config, indent=2, ensure_ascii=False),
                "telegramonly-hysteria2-singbox.json",
                "TelegramOnly sing-box config (Hysteria2)"
            )
            return

        if data == "tgc_export_clash_reality":
            config = telegram_capsule_export.export_clash_meta_config("reality")
            await self._reply_export_file(
                query.message,
                config,
                "telegramonly-reality-clash.yaml",
                "TelegramOnly Clash Meta config (Reality)"
            )
            return

        if data == "tgc_export_clash_hy2":
            config = telegram_capsule_export.export_clash_meta_config("hysteria2")
            await self._reply_export_file(
                query.message,
                config,
                "telegramonly-hysteria2-clash.yaml",
                "TelegramOnly Clash Meta config (Hysteria2)"
            )
            return

        # === MTProto export callbacks ===
        if data == "mt_export_tg_link":
            link = mtproto_manager.generate_tg_link()
            if link:
                await query.message.reply_text(
                    f"📡 *MTProto tg link:*\n`{self._escape_md2(link)}`",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await query.message.reply_text("❌ Ссылка недоступна (не настроен сервер или секрет)")
            return

        if data == "mt_export_https_link":
            link = mtproto_manager.generate_https_link()
            if link:
                await query.message.reply_text(
                    f"📡 *MTProto HTTPS link:*\n`{self._escape_md2(link)}`",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await query.message.reply_text("❌ Ссылка недоступна")
            return

        if data == "mt_export_apisb":
            apisb = mtproto_manager.export_apisb_profile()
            await query.message.reply_text(
                f"📲 *ApiXgRPC Profile \\(MTProto\\):*\n```json\n{json.dumps(apisb, indent=2)}\n```",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        if data == "mt_export_sub_base64":
            sub = mtproto_manager.export_subscription_base64()
            if sub:
                await self._reply_export_file(
                    query.message,
                    sub,
                    "mtproto-subscription-base64.txt",
                    "📦 Subscription (base64)"
                )
            else:
                await query.message.reply_text("❌ Нет данных для subscription")
            return

        if data == "mt_export_qr_menu":
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды MTProto доступны только администратору.")
                return
            await self._show_mt_qr_selection(query.message)
            return

        if data.startswith("mt_export_qr_name:"):
            if not self._is_admin(query.from_user.id):
                await query.message.reply_text("⛔ QR-коды MTProto доступны только администратору.")
                return
            client_name = data.split(":", 1)[1]
            await self._reply_mt_qr(query.message, client_name)
            return

        if data == "vless_reset_confirm":
            success, message = vless_manager.reset_config()
            await query.message.edit_text(message)
            return
        
        # === Xray restart after port change ===
        if data == "xray_restart_after_port":
            await query.answer("⏳ Перезапускаю Xray...")
            
            success, message = vless_manager.restart_xray()
            
            # Обновляем сообщение с результатом
            original_text = query.message.text
            new_text = f"{original_text}\n\n{'✅'if success else '❌'} Перезапуск: {message}"
            
            await query.edit_message_text(
                text=new_text,
                reply_markup=None  # Убираем кнопку
            )
            return
        
        if data == "vless_reset_cancel":
            await query.message.edit_text("❌ Сброс конфигурации отменён")
            return
    
    # === ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ===
    
    async def _show_api_key(self, update: Update, app_id: str):
        """Показать API ключ для app_id (маскированный)."""
        try:
            from app_keys import get_api_key, has_api_key
            
            if app_id == "default":
                api_key = os.getenv("API_SECRET_KEY", "")
                source = "из \\.env"
            else:
                api_key = get_api_key(app_id)
                # Проверяем, есть ли индивидуальный ключ для этого app_id
                if has_api_key(app_id):
                    source = "индивидуальный"
                else:
                    source = "дефолтный"
            
            if api_key:
                masked = self._mask_secret(api_key).replace(".", "\\.")
                message = f"🔑 API ключ \\({source}\\):\n\n`{masked}`"
                if self._secret_reveal_allowed():
                    keyboard = [[InlineKeyboardButton("👁️ Показать полностью", callback_data=f"show_full_api_key:{app_id}")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                else:
                    message += "\n\n⚠️ Полный вывод секретов через Telegram отключён по умолчанию\\."
                    await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                app_id_escaped = escape_markdown(app_id)
                message = f"❌ API ключ не найден для {app_id_escaped}"
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error showing API key: {e}")
            await update.callback_query.message.reply_text("Ошибка при получении API ключа")
    
    async def _show_full_api_key(self, update: Update, app_id: str):
        """Показать полный API ключ для app_id."""
        try:
            if not self._secret_reveal_allowed():
                await update.callback_query.message.reply_text(
                    "⛔ Полный вывод API ключей через Telegram отключён. "
                    "Если это действительно нужно, включите `TELEGRAMONLY_ALLOW_SECRET_REVEAL=true` только временно на сервере."
                )
                return

            from app_keys import get_api_key, has_api_key
            
            if app_id == "default":
                api_key = os.getenv("API_SECRET_KEY", "")
                source = "из \\.env"
            else:
                api_key = get_api_key(app_id)
                # Проверяем, есть ли индивидуальный ключ для этого app_id
                if has_api_key(app_id):
                    source = "индивидуальный"
                else:
                    source = "дефолтный"
            
            # URL API сервера
            api_url = os.getenv("API_URL", "http://localhost:8000/ai_query")
            
            if api_key:
                message = f"""🔑 API ключ \\({source}\\):

📍 *URL:*
`{api_url}`

🔐 *API Key:*
`{api_key}`

⚠️ _Скопируйте и удалите это сообщение_"""
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                app_id_escaped = escape_markdown(app_id)
                message = f"❌ API ключ не найден для {app_id_escaped}"
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error showing full API key: {e}")
            await update.callback_query.message.reply_text("Ошибка при получении API ключа")
    
    async def _show_encryption_key(self, update: Update, app_id: str):
        """Показать ключ шифрования для app_id (маскированный)."""
        try:
            from app_keys import get_encryption_key, has_encryption_key
            
            if app_id == "default":
                enc_key = os.getenv("ENCRYPTION_KEY", "")
                source = "из \\.env"
            else:
                enc_key = get_encryption_key(app_id, force_reload=True)
                # Проверяем, есть ли индивидуальный ключ для этого app_id
                if has_encryption_key(app_id, force_reload=True):
                    source = "индивидуальный"
                else:
                    source = "дефолтный"
            
            if enc_key:
                masked = self._mask_secret(enc_key).replace(".", "\\.")
                message = f"🔐 Ключ шифрования \\({source}\\):\n\n`{masked}`"
                if self._secret_reveal_allowed():
                    keyboard = [[InlineKeyboardButton("👁️ Показать полностью", callback_data=f"show_full_enc_key:{app_id}")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
                else:
                    message += "\n\n⚠️ Полный вывод секретов через Telegram отключён по умолчанию\\."
                    await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                app_id_escaped = escape_markdown(app_id)
                message = f"❌ Ключ шифрования не найден для {app_id_escaped}"
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error showing encryption key: {e}")
            await update.callback_query.message.reply_text("Ошибка при получении ключа шифрования")
    
    async def _show_full_encryption_key(self, update: Update, app_id: str):
        """Показать полный ключ шифрования для app_id."""
        try:
            if not self._secret_reveal_allowed():
                await update.callback_query.message.reply_text(
                    "⛔ Полный вывод ключей шифрования через Telegram отключён. "
                    "Если это действительно нужно, включите `TELEGRAMONLY_ALLOW_SECRET_REVEAL=true` только временно на сервере."
                )
                return

            from app_keys import get_encryption_key, has_encryption_key
            
            if app_id == "default":
                enc_key = os.getenv("ENCRYPTION_KEY", "")
                source = "из \\.env"
            else:
                enc_key = get_encryption_key(app_id, force_reload=True)
                # Проверяем, есть ли индивидуальный ключ для этого app_id
                if has_encryption_key(app_id, force_reload=True):
                    source = "индивидуальный"
                else:
                    source = "дефолтный"
            
            if enc_key:
                message = f"🔐 Ключ шифрования \\({source}\\):\n\n`{enc_key}`\n\n⚠️ _Скопируйте и удалите это сообщение_"
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                app_id_escaped = escape_markdown(app_id)
                message = f"❌ Ключ шифрования не найден для {app_id_escaped}"
                await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error showing full encryption key: {e}")
            await update.callback_query.message.reply_text("Ошибка при получении ключа шифрования")
    
    async def _generate_api_key(self, update: Update, app_id: str):
        """Сгенерировать новый API ключ."""
        try:
            new_key = secrets.token_hex(32)
            
            if app_id == "default":
                if not self._secret_reveal_allowed():
                    await update.callback_query.message.reply_text(
                        "⛔ Генерация дефолтного API ключа через Telegram отключена в безопасном режиме.\n"
                        "Сгенерируйте ключ локально на сервере и обновите `API_SECRET_KEY` в `.env`."
                    )
                    return

                message = f"""✅ Новый API ключ сгенерирован:

`{new_key}`

⚠️ Добавьте в \\.env как API\\_SECRET\\_KEY
🔄 После изменения \\.env перезапустите контейнер"""
            else:
                from app_keys import set_api_key
                set_api_key(app_id, new_key)
                app_id_escaped = escape_markdown(app_id)
                masked = self._mask_secret(new_key).replace(".", "\\.")
                if self._secret_reveal_allowed():
                    message = f"""✅ API ключ для {app_id_escaped} сгенерирован и сохранён:

`{new_key}`

💾 Сохранено в app\\_keys\\.json
🔄 Изменения применятся при следующем запросе"""
                else:
                    message = f"""✅ API ключ для {app_id_escaped} сгенерирован и сохранён:

`{masked}`

⚠️ Полный секрет не отправляется через Telegram
💾 Сохранено в app\\_keys\\.json"""
            
            await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error generating API key: {e}")
            await update.callback_query.message.reply_text("Ошибка при генерации API ключа")
    
    async def _generate_encryption_key(self, update: Update, app_id: str):
        """Сгенерировать новый ключ шифрования."""
        try:
            new_key = secrets.token_hex(32)
            
            if app_id == "default":
                if not self._secret_reveal_allowed():
                    await update.callback_query.message.reply_text(
                        "⛔ Генерация дефолтного ключа шифрования через Telegram отключена в безопасном режиме.\n"
                        "Сгенерируйте ключ локально на сервере и обновите `ENCRYPTION_KEY` в `.env`."
                    )
                    return

                message = f"""✅ Новый ключ шифрования сгенерирован:

`{new_key}`

⚠️ Добавьте в \\.env как ENCRYPTION\\_KEY
🔄 После изменения \\.env перезапустите контейнер"""
            else:
                from app_keys import set_encryption_key
                set_encryption_key(app_id, new_key)
                app_id_escaped = escape_markdown(app_id)
                masked = self._mask_secret(new_key).replace(".", "\\.")
                if self._secret_reveal_allowed():
                    message = f"""✅ Ключ шифрования для {app_id_escaped} сгенерирован и сохранён:

`{new_key}`

💾 Сохранено в app\\_keys\\.json
🔄 Изменения применятся при следующем запросе"""
                else:
                    message = f"""✅ Ключ шифрования для {app_id_escaped} сгенерирован и сохранён:

`{masked}`

⚠️ Полный секрет не отправляется через Telegram
💾 Сохранено в app\\_keys\\.json"""
            
            await update.callback_query.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error generating encryption key: {e}")
            await update.callback_query.message.reply_text("Ошибка при генерации ключа шифрования")
    
    async def _delete_api_key(self, update: Update, app_id: str):
        """Удалить API ключ."""
        try:
            from app_keys import delete_api_key
            
            if delete_api_key(app_id):
                message = f"✅ API ключ для {app_id} удалён"
            else:
                message = f"❌ Не удалось удалить API ключ для {app_id}"
            
            await update.callback_query.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error deleting API key: {e}")
            await update.callback_query.message.reply_text("Ошибка при удалении API ключа")
    
    async def _delete_encryption_key(self, update: Update, app_id: str):
        """Удалить ключ шифрования."""
        try:
            from app_keys import delete_encryption_key
            
            if delete_encryption_key(app_id):
                message = f"✅ Ключ шифрования для {app_id} удалён"
            else:
                message = f"❌ Не удалось удалить ключ шифрования для {app_id}"
            
            await update.callback_query.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error deleting encryption key: {e}")
            await update.callback_query.message.reply_text("Ошибка при удалении ключа шифрования")
    
    async def _show_model_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, provider: str):
        """Показать выбор модели для провайдера."""
        try:
            models = get_available_models(provider)
            current_model = get_current_model(provider)
            
            keyboard = []
            for model in models:
                label = f"✅ {model}" if model == current_model else model
                keyboard.append([InlineKeyboardButton(label, callback_data=f"model_set_{provider}_{model}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.message.edit_text(
                f"🤖 Выберите модель для {provider.upper()}:",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error showing model selection: {e}")
            await update.callback_query.message.edit_text("Ошибка при загрузке списка моделей")
    
    # ================================================================
    # HYSTERIA2 COMMANDS
    # ================================================================

    def _escape_md2(self, text):
        """Экранирование спецсимволов для Telegram Markdown V2."""
        if not text:
            return "не настроен"
        text = str(text)
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(char, f'\\{char}')
        return text

    async def hy2_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_status — показать статус Hysteria2."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            logger.info(f"Admin {user.id} requested Hysteria2 status")
            status = hysteria2_manager.get_status()

            esc = self._escape_md2
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"

            message = f"""⚡ *Hysteria2 Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{esc(status.get("server"))}`
• Порт: `{esc(status.get("port", 443))}` \\(UDP\\)
• SNI: `{esc(status.get("sni") or "(авто)")}`
• Insecure: {"да ⚠️" if status.get("insecure") else "нет ✅"}

*Обфускация:* {("✅ " + esc(status.get("obfs_type", ""))) if status.get("has_obfs") else "❌ выключена"}
*Скорость:* ↑ {status.get("up_mbps", 0) or "авто"} / ↓ {status.get("down_mbps", 0) or "авто"} Mbps
*Masquerade:* `{esc(status.get("masquerade_url", ""))}`
*Пароль:* {"✅" if status["has_password"] else "❌"}
*Клиентов:* {status.get("clients_count", 0)}

*Обновлено:* {esc(status.get("updated_at", "никогда"))}"""

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in hy2_status: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_on — включить Hysteria2."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_on: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_off — выключить Hysteria2."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_off: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_config — показать текущую конфигурацию."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = hysteria2_manager.get_config(include_secrets=False)
            config_str = json.dumps(config, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"⚡ Конфигурация Hysteria2:\n```json\n{config_str}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in hy2_config: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_server <ip> — установить сервер."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            server = args[0] if args else None
            success, message = hysteria2_manager.set_server(server)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_server: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_port <port> — установить порт."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /hy2_set_port <port>")
                return
            try:
                port = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Порт должен быть числом")
                return
            success, message = hysteria2_manager.set_port(port)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_port: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_password <pass> — установить пароль."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /hy2_set_password <password>")
                return
            password = args[0]
            success, message = hysteria2_manager.set_password(password)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_password: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_obfs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_obfs <type> <password> — установить обфускацию."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text(
                    "Использование:\n"
                    "/hy2_set_obfs salamander <password> — включить\n"
                    "/hy2_set_obfs off — выключить"
                )
                return
            obfs_type = args[0]
            if obfs_type == "off":
                success, message = hysteria2_manager.set_obfs("", "")
            else:
                obfs_password = args[1] if len(args) > 1 else ""
                success, message = hysteria2_manager.set_obfs(obfs_type, obfs_password)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_obfs: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_speed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_speed <up> <down> — установить скорость (Mbps)."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if len(args) < 2:
                await update.message.reply_text("Использование: /hy2_set_speed <up_mbps> <down_mbps>\n0 = авто")
                return
            try:
                up = int(args[0])
                down = int(args[1])
            except ValueError:
                await update.message.reply_text("❌ Скорость должна быть числом")
                return
            success, message = hysteria2_manager.set_speed(up, down)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_speed: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_set_masquerade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_set_masquerade <url> — установить URL маскировки."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /hy2_set_masquerade <url>")
                return
            success, message = hysteria2_manager.set_masquerade(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_set_masquerade: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_gen_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_gen_password — сгенерировать и установить пароль."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            password = hysteria2_manager.generate_password()
            success, message = hysteria2_manager.set_password(password)
            if success:
                await update.message.reply_text(f"{message}\n🔑 Пароль: `{password}`",
                                               parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_gen_password: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_gen_cert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_gen_cert — сгенерировать TLS сертификат."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Генерация TLS сертификата...")
            success, message = hysteria2_manager.generate_self_signed_cert()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_gen_cert: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_gen_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_gen_all — сгенерировать всё (пароль + сертификат + IP)."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Генерация пароля, сертификата и определение IP...")
            success, data, message = hysteria2_manager.generate_all()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_gen_all: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_add_client <name> — добавить клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /hy2_add_client <имя>")
                return
            name = args[0]
            success, message, client = hysteria2_manager.add_client(name)
            if success and client:
                uri = hysteria2_manager.generate_hy2_uri(name, client.get("password"), f"Hysteria2-{name}")
                message += f"\n🔗 URI: `{uri}`"
            await update.message.reply_text(message)
            if success and client:
                await self._reply_hy2_qr(update.message, client.get("password", name))
        except Exception as e:
            logger.error(f"Error in hy2_add_client: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_qr - показать QR для Hysteria2-клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ QR-коды Hysteria2 доступны только администратору.")
                return

            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /hy2_qr <client_name_or_password>")
                return

            await self._reply_hy2_qr(update.message, args[0])
        except Exception as e:
            logger.error(f"Error in hy2_qr: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_del_client <name> — удалить клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /hy2_del_client <имя>")
                return
            success, message = hysteria2_manager.remove_client(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_del_client: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_list_clients — список клиентов."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            clients = hysteria2_manager.list_clients()
            if not clients:
                await update.message.reply_text("📋 Клиентов нет")
                return
            lines = ["⚡ *Клиенты Hysteria2:*\n"]
            for i, c in enumerate(clients, 1):
                name = c.get("name", "?")
                pw = c.get("password", "")
                masked = f"{pw[:4]}..." if len(pw) > 4 else "***"
                created = c.get("created_at", "")[:10]
                lines.append(f"{i}\\. `{self._escape_md2(name)}` — пароль: `{self._escape_md2(masked)}` \\({self._escape_md2(created)}\\)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in hy2_list_clients: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_install(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_install — установить Hysteria2 на сервер."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Установка Hysteria2...")
            success, message = hysteria2_manager.install_hysteria2()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_install: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_apply — применить конфиг к серверу."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.apply_config()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_apply: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_start — запустить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.service_control("start")
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in hy2_start: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_stop — остановить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.service_control("stop")
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_stop: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_restart — перезапустить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = hysteria2_manager.service_control("restart")
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in hy2_restart: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_logs — показать логи."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            lines_count = int(args[0]) if args else 30
            success, output = hysteria2_manager.get_logs(lines_count)
            await update.message.reply_text(f"📋 Логи Hysteria2:\n```\n{output}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in hy2_logs: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def hy2_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /hy2_export — экспорт конфигураций."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            logger.info(f"Admin {update.effective_user.id} exporting Hysteria2 config")

            # Generate all export formats
            uri = hysteria2_manager.generate_hy2_uri()
            client_config = hysteria2_manager.export_client_config()
            singbox_config = hysteria2_manager.export_singbox_config()
            server_yaml = hysteria2_manager.export_server_config_yaml()

            esc = self._escape_md2

            parts = [f"⚡ *Hysteria2 Export*\n"]

            if uri:
                parts.append(f"*URI \\(для клиента\\):*\n`{esc(uri)}`\n")

            parts.append(f"*Client Config \\(native\\):*\n```json\n{json.dumps(client_config, indent=2)}\n```\n")
            parts.append(f"*Sing\\-Box Config:*\n```json\n{json.dumps(singbox_config, indent=2)}\n```\n")
            parts.append(f"*Server Config \\(YAML\\):*\n```yaml\n{server_yaml}\n```")

            keyboard = [
                [InlineKeyboardButton("📲 ApiXgRPC Profile", callback_data="hy2_export_apisb")],
                [InlineKeyboardButton("📷 QR по клиенту", callback_data="hy2_export_qr_menu")],
                [InlineKeyboardButton("🧩 Sing-box Config", callback_data="hy2_export_singbox")],
                [InlineKeyboardButton("🧩 Clash Meta Config", callback_data="hy2_export_clash")],
                [InlineKeyboardButton("🖥️ Server Config (YAML)", callback_data="hy2_export_server")],
                [InlineKeyboardButton("📦 Subscription (base64)", callback_data="hy2_export_sub_base64")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = "\n".join(parts)
            # Telegram has 4096 char limit — split if needed
            if len(message) > 4000:
                # Send URI first
                if uri:
                    await update.message.reply_text(f"⚡ *Hysteria2 URI:*\n`{esc(uri)}`",
                                                   parse_mode=ParseMode.MARKDOWN_V2)
                # Send configs as file-like message with buttons
                await update.message.reply_text(
                    f"```json\n{json.dumps(client_config, indent=2)}\n```",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2,
                                                reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in hy2_export: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def tgcapsule_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tgcapsule_export — экспорт TelegramOnly профилей."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            message = (
                "🧭 *TelegramOnly Export*\n\n"
                "Эти профили используют `Reality` и/или `Hysteria2` как транспорт,\n"
                "а правило маршрутизации отправляет через прокси только Telegram-домены.\n\n"
                "*Доступно:*\n"
                "• ApiXgRPC policy profile \\(v2\\)\n"
                "• sing\\-box Telegram\\-only config\n"
                "• Clash Meta Telegram\\-only config\n"
            )

            keyboard = [
                [InlineKeyboardButton("📲 ApiXgRPC v2 (Reality)", callback_data="tgc_export_apix_reality")],
                [InlineKeyboardButton("📲 ApiXgRPC v2 (Hysteria2)", callback_data="tgc_export_apix_hy2")],
                [InlineKeyboardButton("📲 ApiXgRPC v2 (Auto)", callback_data="tgc_export_apix_auto")],
                [InlineKeyboardButton("🧩 sing-box (Reality)", callback_data="tgc_export_sb_reality")],
                [InlineKeyboardButton("🧩 sing-box (Hysteria2)", callback_data="tgc_export_sb_hy2")],
                [InlineKeyboardButton("🧩 Clash Meta (Reality)", callback_data="tgc_export_clash_reality")],
                [InlineKeyboardButton("🧩 Clash Meta (Hysteria2)", callback_data="tgc_export_clash_hy2")],
            ]
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.error(f"Error in tgcapsule_export: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    # === MTPROTO PROXY COMMANDS ===

    async def mt_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_status — показать статус MTProto proxy."""
        try:
            user = update.effective_user
            if not self._is_admin(user.id):
                await update.message.reply_text("⛔ Эта команда доступна только администратору.")
                return

            logger.info(f"Admin {user.id} requested MTProto status")
            status = mtproto_manager.get_status()

            esc = self._escape_md2
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"

            message = f"""📡 *MTProto Proxy Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{esc(status.get("server") or "(не задан)")}`
• Порт: `{esc(str(status.get("port", 993)))}` \\(TCP\\)
• Режим: `{esc(status.get("secret_mode_label") or status.get("secret_mode") or "?")}`
• Секрет: {"✅" if status["has_secret"] else "❌"}
• Fake\\-TLS: {"✅ " + esc(status.get("fake_tls_domain", "")) if status.get("is_fake_tls") else "❌ выключен"}
• Тег: `{esc(status.get("tag") or "(нет)")}`
• Воркеры: {status.get("workers", 2)}
• Клиентов: {status.get("clients_count", 0)}

*Обновлено:* {esc(str(status.get("updated_at") or "никогда"))}"""

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_status: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_on — включить MTProto proxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_on: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_off — выключить MTProto proxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_off: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_config — показать текущую конфигурацию."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = mtproto_manager.get_config(include_secrets=False)
            config_str = json.dumps(config, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"📡 Конфигурация MTProto:\n```json\n{config_str}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_config: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_server <ip> — установить сервер."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            server = args[0] if args else None
            success, message = mtproto_manager.set_server(server)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_set_server: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_port <port> — установить порт."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /mt_set_port <port>")
                return
            try:
                port = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Порт должен быть числом")
                return
            success, message = mtproto_manager.set_port(port)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_set_port: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_mode <dd_inline|ee_split> — переключить режим MTProto."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text(
                    "Использование: /mt_set_mode <mode>\n"
                    f"Доступно: `{mtproto_manager.SECRET_MODE_DD_INLINE}`, `{mtproto_manager.SECRET_MODE_EE_SPLIT}`\n"
                    "Для новых серверов обычно подходит `ee_split`."
                )
                return
            success, message = mtproto_manager.set_secret_mode(args[0])
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_set_mode: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_domain <domain> — установить fake-TLS домен."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                domains = ", ".join(mtproto_manager.AVAILABLE_FAKE_TLS_DOMAINS)
                await update.message.reply_text(
                    f"Использование: /mt_set_domain <domain>\n"
                    f"Примеры: {domains}"
                )
                return
            success, message = mtproto_manager.set_fake_tls_domain(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_set_domain: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_tag(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_tag <hex> — установить статистический тег."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text(
                    "Использование: /mt_set_tag <hex_tag>\n"
                    "Тег для @MTProxybot (промоутирование прокси).\n"
                    "/mt_set_tag off — удалить тег"
                )
                return
            tag = "" if args[0] == "off" else args[0]
            success, message = mtproto_manager.set_tag(tag)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_set_tag: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_set_workers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_set_workers <n> — установить число воркеров."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /mt_set_workers <1-16>")
                return
            try:
                workers = int(args[0])
            except ValueError:
                await update.message.reply_text("❌ Количество воркеров должно быть числом")
                return
            success, message = mtproto_manager.set_workers(workers)
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_set_workers: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_gen_secret(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_gen_secret [domain] — сгенерировать и установить секрет."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            domain = args[0] if args else None
            new_secret = mtproto_manager.generate_secret(domain)
            success, message = mtproto_manager.set_secret(new_secret)
            if success:
                status = mtproto_manager.get_status()
                await update.message.reply_text(
                    f"{message}\n🔑 Секрет: `{new_secret}`\n🧭 Режим: `{status.get('secret_mode_label')}`",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_gen_secret: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_gen_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_gen_all — сгенерировать секрет + определить IP."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Генерация секрета и определение IP...")
            success, data, message = mtproto_manager.generate_all()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_gen_all: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_add_client <name> — добавить клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /mt_add_client <имя>")
                return
            name = args[0]
            success, message, client = mtproto_manager.add_client(name)
            if success and client:
                link = mtproto_manager.generate_tg_link(client.get("secret"))
                if link:
                    message += f"\n🔗 Ссылка: `{link}`"
            await update.message.reply_text(message)
            if success and client:
                await self._reply_mt_qr(update.message, client.get("secret", name))
        except Exception as e:
            logger.error(f"Error in mt_add_client: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_qr - показать QR для MTProto-клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ QR-коды MTProto доступны только администратору.")
                return
            args = context.args or []
            if len(args) != 1:
                await update.message.reply_text("Использование: /mt_qr <client_name_or_secret>")
                return
            await self._reply_mt_qr(update.message, args[0])
        except Exception as e:
            logger.error(f"Error in mt_qr: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_del_client <name> — удалить клиента."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /mt_del_client <имя>")
                return
            success, message = mtproto_manager.remove_client(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_del_client: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_list_clients — список клиентов."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            clients = mtproto_manager.list_clients()
            if not clients:
                await update.message.reply_text("📋 Клиентов нет")
                return
            lines = ["📡 *Клиенты MTProto:*\n"]
            status = mtproto_manager.get_status()
            lines.append(f"*Режим:* `{self._escape_md2(status.get('secret_mode_label') or status.get('secret_mode') or '?')}`\n")
            for i, c in enumerate(clients, 1):
                name = c.get("name", "?")
                secret = c.get("secret", "")
                masked = f"{secret[:6]}..." if len(secret) > 6 else "***"
                created = c.get("created_at", "")[:10]
                lines.append(f"{i}\\. `{self._escape_md2(name)}` — секрет: `{self._escape_md2(masked)}` \\({self._escape_md2(created)}\\)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_list_clients: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_install(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_install — установить MTProto proxy на сервер."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Установка MTProto proxy (компиляция из исходников)...")
            success, message = mtproto_manager.install_mtproto()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_install: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_apply — применить конфиг (записать systemd unit, перезапустить)."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.apply_config()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_apply: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_start — запустить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.service_control("start")
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_start: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_stop — остановить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.service_control("stop")
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_stop: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_restart — перезапустить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = mtproto_manager.service_control("restart")
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_restart: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_logs [n] — показать логи."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            lines_count = int(args[0]) if args else 30
            success, output = mtproto_manager.get_logs(lines_count)
            await update.message.reply_text(f"📋 Логи MTProto:\n```\n{output}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in mt_logs: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_fetch_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_fetch_config — обновить proxy-secret и proxy-multi.conf."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Загрузка proxy-secret и proxy-multi.conf...")
            success, message = mtproto_manager.fetch_proxy_config()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in mt_fetch_config: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def mt_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mt_export — экспорт ссылок и конфигов."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            logger.info(f"Admin {update.effective_user.id} exporting MTProto config")

            esc = self._escape_md2

            tg_link = mtproto_manager.generate_tg_link()
            https_link = mtproto_manager.generate_https_link()
            status = mtproto_manager.get_status()

            parts = ["📡 *MTProto Export*\n"]
            parts.append(f"*Режим:* `{esc(status.get('secret_mode_label') or status.get('secret_mode') or '?')}`\n")

            if tg_link:
                parts.append(f"*tg link \\(для Telegram\\):*\n`{esc(tg_link)}`\n")
            if https_link:
                parts.append(f"*HTTPS link:*\n`{esc(https_link)}`\n")

            if not tg_link and not https_link:
                parts.append("❌ Не настроен сервер или секрет")

            keyboard = [
                [InlineKeyboardButton("📲 tg:// Link", callback_data="mt_export_tg_link")],
                [InlineKeyboardButton("🌐 HTTPS Link", callback_data="mt_export_https_link")],
                [InlineKeyboardButton("📷 QR по клиенту", callback_data="mt_export_qr_menu")],
                [InlineKeyboardButton("📲 ApiXgRPC Profile", callback_data="mt_export_apisb")],
                [InlineKeyboardButton("📦 Subscription (base64)", callback_data="mt_export_sub_base64")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = "\n".join(parts)
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2,
                                            reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in mt_export: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    # === ERROR HANDLER ===

    async def naive_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_status — показать состояние NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            status = naiveproxy_manager.get_status()
            enabled = "🟢 включен" if status.get("enabled") else "🔴 выключен"
            configured = "да" if status.get("configured") else "нет"
            systemd = status.get("systemd_output") or "unknown"
            text = (
                "🌐 NaiveProxy status\n\n"
                f"Состояние: {enabled}\n"
                f"Сконфигурирован: {configured}\n"
                f"Домен: {status.get('domain') or '-'}\n"
                f"Порт: {status.get('port')}\n"
                f"Пользователь: {status.get('username') or '-'}\n"
                f"Service: {status.get('service_name')}\n"
                f"systemd: {systemd}"
            )
            await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Error in naive_status: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_on — включить NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = naiveproxy_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_on: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_off — выключить NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = naiveproxy_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_off: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_config — показать текущий конфиг NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = naiveproxy_manager.get_config(include_secrets=self._secret_reveal_allowed())
            text = (
                "🌐 NaiveProxy config\n\n"
                f"enabled: {config.get('enabled')}\n"
                f"domain: {config.get('domain') or '-'}\n"
                f"server: {config.get('server') or '-'}\n"
                f"port: {config.get('port')}\n"
                f"username: {config.get('username') or '-'}\n"
                f"password: {config.get('password') or '-'}\n"
                f"scheme: {config.get('scheme')}\n"
                f"local_socks_port: {config.get('local_socks_port')}\n"
                f"padding: {config.get('padding')}\n"
                f"caddyfile_path: {config.get('caddyfile_path')}\n"
                f"service_name: {config.get('service_name')}"
            )
            await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Error in naive_config: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_set_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_set_domain <domain> — задать домен NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            if not context.args:
                await update.message.reply_text("Использование: /naive_set_domain <domain>")
                return
            success, message = naiveproxy_manager.set_domain(context.args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_set_domain: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_set_port <port> — задать порт NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            if not context.args:
                await update.message.reply_text("Использование: /naive_set_port <port>")
                return
            success, message = naiveproxy_manager.set_port(int(context.args[0]))
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_set_port: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_set_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_set_user <username> — задать пользователя NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            if not context.args:
                await update.message.reply_text("Использование: /naive_set_user <username>")
                return
            success, message = naiveproxy_manager.set_username(context.args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_set_user: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_set_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_set_password <password> — задать пароль NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            if not context.args:
                await update.message.reply_text("Использование: /naive_set_password <password>")
                return
            success, message = naiveproxy_manager.set_password(context.args[0])
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_set_password: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_gen_creds(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_gen_creds — сгенерировать user/password для NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message, creds = naiveproxy_manager.generate_credentials()
            if success:
                await update.message.reply_text(
                    f"{message}\nusername: {creds.get('username')}\npassword: {creds.get('password')}"
                )
            else:
                await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_gen_creds: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_install(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_install — запустить серверную установку NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            await update.message.reply_text("⏳ Установка NaiveProxy...")
            success, message = naiveproxy_manager.install_naiveproxy()
            await update.message.reply_text("✅ Установка завершена" if success else "❌ Установка завершилась с ошибкой")
            await self._reply_export_file(
                update.message,
                message,
                "naive-install.log",
                "NaiveProxy install output",
            )
        except Exception as e:
            logger.error(f"Error in naive_install: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_uri(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_uri — показать клиентский URI NaiveProxy."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            uri = naiveproxy_manager.build_client_uri()
            await update.message.reply_text(f"🌐 NaiveProxy URI:\n{uri}")
        except Exception as e:
            logger.error(f"Error in naive_uri: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_apply — записать Caddyfile и перезапустить сервис."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = naiveproxy_manager.apply_server_config()
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Error in naive_apply: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def naive_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /naive_export — экспорт клиента и профиля для ApiNgRPC."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            client_config = naiveproxy_manager.export_client_config()
            aping_profile = naiveproxy_manager.export_aping_profile()
            uri = naiveproxy_manager.build_client_uri()
            await update.message.reply_text(f"🌐 NaiveProxy URI:\n{uri}")
            await self._reply_export_file(
                update.message,
                json.dumps(client_config, ensure_ascii=False, indent=2),
                "naiveproxy-client.json",
                "NaiveProxy client config",
            )
            await self._reply_export_file(
                update.message,
                aping_profile,
                "aping-naive-profile.json",
                "ApiNgRPC NaiveProxy profile",
            )
        except Exception as e:
            logger.error(f"Error in naive_export: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    # =====================================================================
    # === TUIC COMMANDS ===
    # =====================================================================

    async def tuic_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tuic_status — показать статус TUIC."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            status = tuic_manager.get_status()
            esc = self._escape_md2
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"

            message = f"""🔷 *TUIC Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{esc(status.get("server"))}`
• Порт: `{esc(status.get("port", 443))}` \\(UDP\\)
• SNI: `{esc(status.get("sni") or "(авто)")}`
• Insecure: {"да ⚠️" if status.get("insecure") else "нет ✅"}
• Congestion: `{esc(status.get("congestion_control", "bbr"))}`
• UDP relay: `{esc(status.get("udp_relay_mode", "native"))}`

*Клиентов:* {status.get("clients_count", 0)}
*Обновлено:* {esc(status.get("updated_at", "никогда"))}"""

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"Error in tuic_status: {e}")
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = tuic_manager.get_config(include_secrets=False)
            config_str = json.dumps(config, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"🔷 Конфигурация TUIC:\n```json\n{config_str}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            server = args[0] if args else None
            success, message = tuic_manager.set_server(server)
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /tuic_set_port <порт>")
                return
            port = int(args[0])
            success, message = tuic_manager.set_port(port)
            await update.message.reply_text(message)
        except ValueError:
            await update.message.reply_text("❌ Порт должен быть числом")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_set_cc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tuic_set_cc <bbr|cubic|new_reno>."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /tuic_set_cc <bbr|cubic|new_reno>")
                return
            success, message = tuic_manager.set_congestion_control(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_gen_cert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.generate_self_signed_cert()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_gen_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, results, message = tuic_manager.generate_all()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tuic_add <name>."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /tuic_add <имя>")
                return
            name = args[0]
            success, message, client = tuic_manager.add_client(name)
            if success and client:
                uri = tuic_manager.generate_tuic_uri(
                    client.get("uuid", ""), client.get("password", ""), f"TUIC-{name}")
                message += f"\n🔗 URI: `{uri}`"
            await update.message.reply_text(message)
            if success and client:
                await self._reply_tuic_qr(update.message, name)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /tuic_qr <имя_клиента>")
                return
            await self._reply_tuic_qr(update.message, args[0])
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /tuic_del <имя>")
                return
            success, message = tuic_manager.remove_client(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            clients = tuic_manager.list_clients()
            if not clients:
                await update.message.reply_text("📋 Клиентов TUIC нет")
                return
            esc = self._escape_md2
            lines = ["🔷 *Клиенты TUIC:*\n"]
            for i, c in enumerate(clients, 1):
                name = c.get("name", "?")
                uuid_short = c.get("uuid", "")[:8] + "..."
                created = c.get("created_at", "")[:10]
                lines.append(f"{i}\\. `{esc(name)}` — uuid: `{esc(uuid_short)}` \\({esc(created)}\\)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.apply_config()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.service_control("start")
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.service_control("stop")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = tuic_manager.service_control("restart")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            lines_count = int(args[0]) if args else 30
            success, output = tuic_manager.get_logs(lines_count)
            await update.message.reply_text(f"📋 Логи TUIC:\n```\n{output}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def tuic_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /tuic_export — экспорт конфигураций."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            singbox_config = tuic_manager.export_singbox_config()
            server_config = tuic_manager.export_server_config_json()

            await self._reply_export_file(
                update.message,
                json.dumps(singbox_config, ensure_ascii=False, indent=2),
                "tuic-singbox-client.json",
                "🔷 TUIC sing-box client config",
            )
            await self._reply_export_file(
                update.message,
                server_config,
                "tuic-server-config.json",
                "🔷 TUIC server config (sing-box)",
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # =====================================================================
    # === ANYTLS COMMANDS ===
    # =====================================================================

    async def anytls_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /anytls_status — показать статус AnyTLS."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            status = anytls_manager.get_status()
            esc = self._escape_md2
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"

            message = f"""🔶 *AnyTLS Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{esc(status.get("server"))}`
• Порт: `{esc(status.get("port", 443))}` \\(TCP\\)
• SNI: `{esc(status.get("sni") or "(авто)")}`
• Insecure: {"да ⚠️" if status.get("insecure") else "нет ✅"}

*Клиентов:* {status.get("clients_count", 0)}
*Обновлено:* {esc(status.get("updated_at", "никогда"))}"""

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = anytls_manager.get_config(include_secrets=False)
            config_str = json.dumps(config, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"🔶 Конфигурация AnyTLS:\n```json\n{config_str}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            server = args[0] if args else None
            success, message = anytls_manager.set_server(server)
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /anytls_set_port <порт>")
                return
            port = int(args[0])
            success, message = anytls_manager.set_port(port)
            await update.message.reply_text(message)
        except ValueError:
            await update.message.reply_text("❌ Порт должен быть числом")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_gen_cert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.generate_self_signed_cert()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_gen_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, results, message = anytls_manager.generate_all()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /anytls_add <name>."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /anytls_add <имя>")
                return
            name = args[0]
            success, message, client = anytls_manager.add_client(name)
            if success and client:
                uri = anytls_manager.generate_anytls_uri(
                    client.get("password", ""), f"AnyTLS-{name}")
                message += f"\n🔗 URI: `{uri}`"
            await update.message.reply_text(message)
            if success and client:
                await self._reply_anytls_qr(update.message, name)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /anytls_qr <имя_клиента>")
                return
            await self._reply_anytls_qr(update.message, args[0])
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /anytls_del <имя>")
                return
            success, message = anytls_manager.remove_client(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            clients = anytls_manager.list_clients()
            if not clients:
                await update.message.reply_text("📋 Клиентов AnyTLS нет")
                return
            esc = self._escape_md2
            lines = ["🔶 *Клиенты AnyTLS:*\n"]
            for i, c in enumerate(clients, 1):
                name = c.get("name", "?")
                pw = c.get("password", "")
                masked = f"{pw[:4]}..." if len(pw) > 4 else "***"
                created = c.get("created_at", "")[:10]
                lines.append(f"{i}\\. `{esc(name)}` — пароль: `{esc(masked)}` \\({esc(created)}\\)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.apply_config()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.service_control("start")
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.service_control("stop")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = anytls_manager.service_control("restart")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            lines_count = int(args[0]) if args else 30
            success, output = anytls_manager.get_logs(lines_count)
            await update.message.reply_text(f"📋 Логи AnyTLS:\n```\n{output}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def anytls_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            singbox_config = anytls_manager.export_singbox_config()
            server_config = anytls_manager.export_server_config_json()

            await self._reply_export_file(
                update.message,
                json.dumps(singbox_config, ensure_ascii=False, indent=2),
                "anytls-singbox-client.json",
                "🔶 AnyTLS sing-box client config",
            )
            await self._reply_export_file(
                update.message,
                server_config,
                "anytls-server-config.json",
                "🔶 AnyTLS server config (sing-box)",
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # =====================================================================
    # === XHTTP COMMANDS ===
    # =====================================================================

    async def xhttp_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xhttp_status — показать статус XHTTP."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            status = xhttp_manager.get_status()
            esc = self._escape_md2
            status_emoji = "🟢" if status["enabled"] else "🔴"
            config_emoji = "✅" if status["configured"] else "❌"

            message = f"""🌐 *XHTTP Статус*

*Состояние:* {status_emoji} {"Включён" if status["enabled"] else "Выключен"}
*Конфигурация:* {config_emoji} {"Настроена" if status["configured"] else "Не настроена"}

*Параметры:*
• Сервер: `{esc(status.get("server"))}`
• Порт: `{esc(status.get("port", 443))}` \\(TCP\\)
• Path: `{esc(status.get("path", "/"))}`
• Host: `{esc(status.get("host") or "(пусто)")}`
• Mode: `{esc(status.get("mode", "auto"))}`
• Security: `{esc(status.get("security", "tls"))}`
• SNI: `{esc(status.get("sni") or "(авто)")}`
• Insecure: {"да ⚠️" if status.get("insecure") else "нет ✅"}

*Клиентов:* {status.get("clients_count", 0)}
*Обновлено:* {esc(status.get("updated_at", "никогда"))}"""

            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_on(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.enable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.disable()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            config = xhttp_manager.get_config(include_secrets=False)
            config_str = json.dumps(config, ensure_ascii=False, indent=2)
            await update.message.reply_text(f"🌐 Конфигурация XHTTP:\n```json\n{config_str}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_set_server(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            server = args[0] if args else None
            success, message = xhttp_manager.set_server(server)
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_set_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_set_port <порт>")
                return
            port = int(args[0])
            success, message = xhttp_manager.set_port(port)
            await update.message.reply_text(message)
        except ValueError:
            await update.message.reply_text("❌ Порт должен быть числом")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_set_path(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_set_path <path>")
                return
            success, message = xhttp_manager.set_path(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_set_host(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            host = args[0] if args else ""
            success, message = xhttp_manager.set_host(host)
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_set_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_set_mode <auto|packet-up|stream-up>")
                return
            success, message = xhttp_manager.set_mode(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_gen_cert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.generate_self_signed_cert()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_gen_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, results, message = xhttp_manager.generate_all()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_add_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /xhttp_add <name>."""
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_add <имя>")
                return
            name = args[0]
            success, message, client = xhttp_manager.add_client(name)
            if success and client:
                uri = xhttp_manager.generate_xhttp_uri(
                    client.get("uuid", ""), f"XHTTP-{name}")
                message += f"\n🔗 URI: `{uri}`"
            await update.message.reply_text(message)
            if success and client:
                await self._reply_xhttp_qr(update.message, name)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_qr(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_qr <имя_клиента>")
                return
            await self._reply_xhttp_qr(update.message, args[0])
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_del_client(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            if not args:
                await update.message.reply_text("Использование: /xhttp_del <имя>")
                return
            success, message = xhttp_manager.remove_client(args[0])
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_list_clients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            clients = xhttp_manager.list_clients()
            if not clients:
                await update.message.reply_text("📋 Клиентов XHTTP нет")
                return
            esc = self._escape_md2
            lines = ["🌐 *Клиенты XHTTP:*\n"]
            for i, c in enumerate(clients, 1):
                name = c.get("name", "?")
                uuid_short = c.get("uuid", "")[:8] + "..."
                created = c.get("created_at", "")[:10]
                lines.append(f"{i}\\. `{esc(name)}` — uuid: `{esc(uuid_short)}` \\({esc(created)}\\)")
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_apply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.apply_config()
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.service_control("start")
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.service_control("stop")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            success, message = xhttp_manager.service_control("restart")
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return
            args = context.args or []
            lines_count = int(args[0]) if args else 30
            success, output = xhttp_manager.get_logs(lines_count)
            await update.message.reply_text(f"📋 Логи XHTTP:\n```\n{output}\n```",
                                           parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def xhttp_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self._is_admin(update.effective_user.id):
                await update.message.reply_text("⛔ Только для администратора.")
                return

            singbox_config = xhttp_manager.export_singbox_config()
            server_config = xhttp_manager.export_server_config_json()

            await self._reply_export_file(
                update.message,
                json.dumps(singbox_config, ensure_ascii=False, indent=2),
                "xhttp-singbox-client.json",
                "🌐 XHTTP sing-box client config",
            )
            await self._reply_export_file(
                update.message,
                server_config,
                "xhttp-server-config.json",
                "🌐 XHTTP server config (sing-box)",
            )
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ошибок."""
        logger.error(f"Update {update} caused error {context.error}")

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке команды. Попробуйте позже."
            )
