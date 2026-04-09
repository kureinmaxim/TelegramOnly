# -*- coding: utf-8 -*-
"""
Упрощённый Telegram бот с поддержкой VLESS-Reality.

Этот модуль содержит минимальную версию бота с командами:
- Базовые: start, help, info, clear
- Админские: управление API ключами, шифрованием, пользователями
- VLESS-Reality: полное управление VLESS конфигурацией
"""

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, filters

from handlers import BotHandlersLite
from config import Config

logger = logging.getLogger(__name__)


class TelegramBotLite:
    """Упрощённый Telegram бот с поддержкой VLESS-Reality."""
    
    def __init__(self, config: Config):
        """Инициализация бота с конфигурацией."""
        self.config = config
        self.handlers = BotHandlersLite(config=self.config)
        self.application = None
    
    async def start(self, blocking: bool = True):
        """Запуск бота."""
        try:
            # Создаём Application
            self.application = Application.builder().token(self.config.bot_token).build()
            
            # Регистрируем обработчики
            self._register_handlers()
            
            # Запускаем бота
            logger.info("Bot Lite is starting...")
            await self.application.initialize()
            await self.application.start()
            
            # Начинаем polling
            logger.info("Bot Lite is now polling for updates...")
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                timeout=self.config.poll_timeout,
                poll_interval=self.config.poll_interval,
            )
            
            if not blocking:
                return
            
            # Держим бота запущенным до прерывания
            import signal
            import asyncio
            
            stop_signals = (signal.SIGINT, signal.SIGTERM)
            loop = asyncio.get_running_loop()
            stop_future = loop.create_future()
            
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}")
                if not stop_future.done():
                    stop_future.set_result(signum)
            
            for sig in stop_signals:
                signal.signal(sig, signal_handler)
            
            try:
                await stop_future
            except Exception as e:
                logger.error(f"Error while waiting: {e}")
            finally:
                logger.info("Stopping bot...")
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            if blocking and self.application:
                await self.application.stop()
                await self.application.shutdown()
    
    async def stop(self):
        """Остановка бота."""
        if self.application:
            logger.info("Stopping bot application...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
    
    def _register_handlers(self):
        """Регистрация всех обработчиков команд."""
        try:
            # === БАЗОВЫЕ КОМАНДЫ ===
            self.application.add_handler(
                CommandHandler("start", self.handlers.start_command)
            )
            self.application.add_handler(
                CommandHandler("help", self.handlers.help_command)
            )
            self.application.add_handler(
                CommandHandler("info", self.handlers.info_command)
            )
            self.application.add_handler(
                CommandHandler("clear", self.handlers.clear_chat)
            )
            
            # === СИСТЕМА И ИНФОРМАЦИЯ (админ) ===
            self.application.add_handler(
                CommandHandler("ver", self.handlers.version_command)
            )
            self.application.add_handler(
                CommandHandler("api", self.handlers.api_command)
            )
            self.application.add_handler(
                CommandHandler("gen_api_key", self.handlers.gen_api_key_command)
            )
            self.application.add_handler(
                CommandHandler("del_api_key", self.handlers.del_api_key_command)
            )
            self.application.add_handler(
                CommandHandler("encryption_key", self.handlers.encryption_key_command)
            )
            self.application.add_handler(
                CommandHandler("gen_encryption_key", self.handlers.gen_encryption_key_command)
            )
            self.application.add_handler(
                CommandHandler("del_encryption_key", self.handlers.del_encryption_key_command)
            )
            self.application.add_handler(
                CommandHandler("gen_chacha_key", self.handlers.gen_chacha_key_command)
            )
            self.application.add_handler(
                CommandHandler("gen_pqc_key", self.handlers.gen_pqc_key_command)
            )
            
            # === УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ (админ) ===
            self.application.add_handler(
                CommandHandler("list_users", self.handlers.admin_list_users)
            )
            self.application.add_handler(
                CommandHandler("setcity", self.handlers.admin_setcity)
            )
            self.application.add_handler(
                CommandHandler("setgreeting", self.handlers.admin_setgreeting)
            )
            self.application.add_handler(
                CommandHandler("special_add", self.handlers.admin_special_add)
            )
            self.application.add_handler(
                CommandHandler("special_remove", self.handlers.admin_special_remove)
            )
            
            # === НАСТРОЙКИ ИИ (админ) ===
            self.application.add_handler(
                CommandHandler("ai_provider", self.handlers.ai_set_provider)
            )
            self.application.add_handler(
                CommandHandler("ch_model", self.handlers.ch_model_command)
            )
            
            # === VLESS-REALITY КОМАНДЫ (админ) ===
            self.application.add_handler(
                CommandHandler("vless_status", self.handlers.vless_status)
            )
            self.application.add_handler(
                CommandHandler("vless_on", self.handlers.vless_on)
            )
            self.application.add_handler(
                CommandHandler("vless_off", self.handlers.vless_off)
            )
            self.application.add_handler(
                CommandHandler("vless_config", self.handlers.vless_config)
            )
            self.application.add_handler(
                CommandHandler("vless_set_server", self.handlers.vless_set_server)
            )
            self.application.add_handler(
                CommandHandler("vless_set_port", self.handlers.vless_set_port)
            )
            self.application.add_handler(
                CommandHandler("vless_add_client", self.handlers.vless_add_client)
            )
            self.application.add_handler(
                CommandHandler("vless_qr", self.handlers.vless_qr)
            )
            self.application.add_handler(
                CommandHandler("vless_list_clients", self.handlers.vless_list_clients)
            )
            self.application.add_handler(
                CommandHandler("vless_del_client", self.handlers.vless_del_client)
            )
            self.application.add_handler(
                CommandHandler("vless_set_uuid", self.handlers.vless_set_uuid)
            )
            self.application.add_handler(
                CommandHandler("vless_set_key", self.handlers.vless_set_key)
            )
            self.application.add_handler(
                CommandHandler("vless_set_shortid", self.handlers.vless_set_shortid)
            )
            self.application.add_handler(
                CommandHandler("vless_set_sni", self.handlers.vless_set_sni)
            )
            self.application.add_handler(
                CommandHandler("vless_set_fingerprint", self.handlers.vless_set_fingerprint)
            )
            self.application.add_handler(
                CommandHandler("vless_gen_keys", self.handlers.vless_gen_keys)
            )
            self.application.add_handler(
                CommandHandler("vless_test", self.handlers.vless_test)
            )
            self.application.add_handler(
                CommandHandler("vless_export", self.handlers.vless_export)
            )
            self.application.add_handler(
                CommandHandler("vless_sync", self.handlers.vless_sync)
            )
            self.application.add_handler(
                CommandHandler("vless_reset", self.handlers.vless_reset)
            )
            
            # === XRAY MANAGEMENT COMMANDS (админ) ===
            self.application.add_handler(
                CommandHandler("xray_status", self.handlers.xray_status)
            )
            self.application.add_handler(
                CommandHandler("xray_config", self.handlers.xray_config)
            )
            self.application.add_handler(
                CommandHandler("xray_install", self.handlers.xray_install)
            )
            self.application.add_handler(
                CommandHandler("xray_apply", self.handlers.xray_apply)
            )
            self.application.add_handler(
                CommandHandler("xray_start", self.handlers.xray_start)
            )
            self.application.add_handler(
                CommandHandler("xray_stop", self.handlers.xray_stop)
            )
            self.application.add_handler(
                CommandHandler("xray_restart", self.handlers.xray_restart)
            )
            self.application.add_handler(
                CommandHandler("xray_logs", self.handlers.xray_logs)
            )

            # === NGINX SNI ROUTING COMMANDS ===
            nginx_commands = {
                "nginx_status": self.handlers.nginx_status,
                "nginx_enable": self.handlers.nginx_enable,
                "nginx_disable": self.handlers.nginx_disable,
                "nginx_set_domain": self.handlers.nginx_set_domain,
                "nginx_config": self.handlers.nginx_config,
            }
            for cmd_name, cmd_handler in nginx_commands.items():
                self.application.add_handler(CommandHandler(cmd_name, cmd_handler))

            # === HEADSCALE COMMANDS ===
            headscale_commands = {
                "headscale_status": self.handlers.headscale_status,
                "headscale_enable": self.handlers.headscale_enable,
                "headscale_disable": self.handlers.headscale_disable,
                "headscale_set_url": self.handlers.headscale_set_url,
                "headscale_gen": self.handlers.headscale_gen,
                "headscale_list_nodes": self.handlers.headscale_list_nodes,
                "headscale_create_user": self.handlers.headscale_create_user,
            }
            for cmd_name, cmd_handler in headscale_commands.items():
                self.application.add_handler(CommandHandler(cmd_name, cmd_handler))

            # === HYSTERIA2 COMMANDS ===
            hy2_commands = {
                "hy2_status": self.handlers.hy2_status,
                "hy2_on": self.handlers.hy2_on,
                "hy2_off": self.handlers.hy2_off,
                "hy2_config": self.handlers.hy2_config,
                "hy2_set_server": self.handlers.hy2_set_server,
                "hy2_set_port": self.handlers.hy2_set_port,
                "hy2_set_password": self.handlers.hy2_set_password,
                "hy2_set_obfs": self.handlers.hy2_set_obfs,
                "hy2_set_speed": self.handlers.hy2_set_speed,
                "hy2_set_masquerade": self.handlers.hy2_set_masquerade,
                "hy2_gen_password": self.handlers.hy2_gen_password,
                "hy2_gen_cert": self.handlers.hy2_gen_cert,
                "hy2_gen_all": self.handlers.hy2_gen_all,
                "hy2_add_client": self.handlers.hy2_add_client,
                "hy2_qr": self.handlers.hy2_qr,
                "hy2_del_client": self.handlers.hy2_del_client,
                "hy2_list_clients": self.handlers.hy2_list_clients,
                "hy2_install": self.handlers.hy2_install,
                "hy2_apply": self.handlers.hy2_apply,
                "hy2_start": self.handlers.hy2_start,
                "hy2_stop": self.handlers.hy2_stop,
                "hy2_restart": self.handlers.hy2_restart,
                "hy2_logs": self.handlers.hy2_logs,
                "hy2_export": self.handlers.hy2_export,
            }
            for cmd_name, handler_func in hy2_commands.items():
                self.application.add_handler(CommandHandler(cmd_name, handler_func))

            # === NAIVEPROXY COMMANDS ===
            naive_commands = {
                "naive_status": self.handlers.naive_status,
                "naive_on": self.handlers.naive_on,
                "naive_off": self.handlers.naive_off,
                "naive_config": self.handlers.naive_config,
                "naive_set_domain": self.handlers.naive_set_domain,
                "naive_set_port": self.handlers.naive_set_port,
                "naive_set_user": self.handlers.naive_set_user,
                "naive_set_password": self.handlers.naive_set_password,
                "naive_gen_creds": self.handlers.naive_gen_creds,
                "naive_install": self.handlers.naive_install,
                "naive_uri": self.handlers.naive_uri,
                "naive_apply": self.handlers.naive_apply,
                "naive_export": self.handlers.naive_export,
            }
            for cmd_name, handler_func in naive_commands.items():
                self.application.add_handler(CommandHandler(cmd_name, handler_func))

            # === TELEGRAMONLY EXPORT COMMANDS ===
            self.application.add_handler(
                CommandHandler("tgcapsule_export", self.handlers.tgcapsule_export)
            )

            # === MTPROTO PROXY COMMANDS ===
            mt_commands = {
                "mt_status": self.handlers.mt_status,
                "mt_on": self.handlers.mt_on,
                "mt_off": self.handlers.mt_off,
                "mt_config": self.handlers.mt_config,
                "mt_set_server": self.handlers.mt_set_server,
                "mt_set_port": self.handlers.mt_set_port,
                "mt_set_mode": self.handlers.mt_set_mode,
                "mt_set_domain": self.handlers.mt_set_domain,
                "mt_set_tag": self.handlers.mt_set_tag,
                "mt_set_workers": self.handlers.mt_set_workers,
                "mt_gen_secret": self.handlers.mt_gen_secret,
                "mt_gen_all": self.handlers.mt_gen_all,
                "mt_add_client": self.handlers.mt_add_client,
                "mt_qr": self.handlers.mt_qr,
                "mt_del_client": self.handlers.mt_del_client,
                "mt_list_clients": self.handlers.mt_list_clients,
                "mt_install": self.handlers.mt_install,
                "mt_apply": self.handlers.mt_apply,
                "mt_start": self.handlers.mt_start,
                "mt_stop": self.handlers.mt_stop,
                "mt_restart": self.handlers.mt_restart,
                "mt_logs": self.handlers.mt_logs,
                "mt_fetch_config": self.handlers.mt_fetch_config,
                "mt_export": self.handlers.mt_export,
            }
            for cmd_name, handler_func in mt_commands.items():
                self.application.add_handler(CommandHandler(cmd_name, handler_func))

            # === CALLBACK QUERY HANDLER ===
            self.application.add_handler(
                CallbackQueryHandler(self.handlers.callback_query_handler)
            )
            
            # === ERROR HANDLER ===
            self.application.add_error_handler(self.handlers.error_handler)
            
            logger.info("All handlers registered successfully")
            
        except Exception as e:
            logger.error(f"Error registering handlers: {e}")
            raise
