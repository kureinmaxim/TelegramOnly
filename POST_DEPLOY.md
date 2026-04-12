# After Deploy TelegramOnly

Короткая памятка для сервера после первого успешного запуска.

---

## 1. Что проверить сразу

На сервере:

```bash
cd /opt/TelegramSimple
docker compose ps | cat
docker logs telegram-helper-lite --tail 50 | cat
```

В Telegram:

```text
/start
/info
/vless_export
```

Если бот отвечает и контейнер стабильно запущен, можно переходить к чистке.

Если у вас уже отдельно настроен `mtproto-proxy` как host service на Debian, обычный post-deploy или redeploy контейнера `telegram-helper-lite` не требует его удаления или переустановки. Проверяйте MTProto отдельно только если меняли его конфиг, режим (`dd_inline` / `ee_split`) или server secret.

---

## 2. Можно ли удалять `CREDENTIALS.txt`

Да, **можно**, но только если вы уже **сохранили все нужные значения** в безопасном месте:

- `API_SECRET_KEY`
- `HMAC_SECRET`
- `ENCRYPTION_KEY`
- пароль `Hysteria2`
- другие одноразово сгенерированные ключи/секреты, если вы ими пользуетесь

Если эти данные уже перенесены:

- в локальный `.env.deploy`
- в менеджер паролей
- или в другой защищённый архив

тогда файл на сервере больше не нужен.

Удаление:

```bash
rm -f /opt/TelegramSimple/CREDENTIALS.txt
```

Важно:

- не удаляйте `CREDENTIALS.txt`, если ещё не сверили все значения
- не храните секреты только в shell history или в чатах

---

## 3. Что обязательно оставить на сервере

Для текущего workflow лучше оставить:

- `compose.yaml`
- `Dockerfile`
- `.env`
- `requirements.txt`
- все основные `.py` файлы проекта
- `users.json`
- `app_keys.json`
- `vless_config.json`
- `hysteria2_config.json`
- `mtproto_config.json`
- `headscale_config.json`
- `bot.log`

Почему: текущий деплой в этом проекте идёт через `docker compose build` из папки `/opt/TelegramSimple`. Если удалить исходники, следующий rebuild на сервере уже не сработает.

Если используете MTProto, также сохраняйте host-side файлы вне папки проекта:

- `/etc/systemd/system/mtproto-proxy.service`
- `/etc/mtproto-proxy/proxy-secret`
- `/etc/mtproto-proxy/proxy-multi.conf`
- `/root/mtproto_client.txt` или другой ваш сохранённый источник client secret

---

## 4. Что можно удалить без вреда для работы

Если бот уже работает и всё проверено, обычно можно удалить:

- случайно загруженный `.env.deploy`
- случайно загруженные `.bashrc`, `.profile`, `.ssh`, `.config`, `.claude`
- `__pycache__`
- `.pytest_cache`
- `.DS_Store`
- `CREDENTIALS.txt` после сохранения секретов

Пример:

```bash
cd /opt/TelegramSimple
rm -rf .bash_history .bashrc .profile .ssh .config .claude .pytest_cache ".DS_Store" "__pycache__"
rm -f .env.deploy
```

---

## 5. Что удалять только если точно не нужно

Удаляйте это только если понимаете последствия:

- `tests/` — не нужен для рантайма, но полезен для проверки
- `dockhand/` — если не используете diagnostics panel
- `compose.headscale.yaml` — если не используете Headscale
- `.md` файлы — не нужны для рантайма, но полезны как локальная документация на сервере
- `scripts/` — не нужны для работы контейнера, но полезны для обслуживания

Если хотите максимально упростить обслуживание, лучше сначала ничего из этого не удалять.

Для MTProto:

- не удаляйте host unit и файлы из `/etc/mtproto-proxy`, если прокси уже рабочий
- не меняйте их во время обычного редеплоя бота без отдельной причины

---

## 6. Минимально безопасная чистка

Если хочется убрать только лишнее и не рисковать:

```bash
cd /opt/TelegramSimple
rm -rf .bash_history .bashrc .profile .ssh .config .claude .pytest_cache ".DS_Store" "__pycache__"
rm -f .env.deploy
rm -f CREDENTIALS.txt
```

Последнюю строку выполняйте **только после сохранения всех секретов**.

---

## 7. Если хотите ещё сильнее упростить сервер

Тогда лучше делать уже не "ручной deploy из папки", а отдельный production-подход:

- собирать Docker image локально или в CI
- пушить image в registry
- на сервере хранить только `compose.yaml`, `.env` и JSON-данные

Но это уже другой workflow, не тот, который сейчас описан в `Deploy TelegramOnly.md`.
