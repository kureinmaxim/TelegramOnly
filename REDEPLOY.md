# Redeploy TelegramOnly

Короткая инструкция для обычного обновления бота на сервере без полного переустановления VPS.

Этот сценарий подходит, если:

- сервер уже настроен
- Docker и `docker compose` уже работают
- проект на сервере лежит в `/opt/TelegramSimple`
- SSH-подключение выполняется на `138.124.71.73:22542`

---

## Что обновляем

При редеплое мы:

1. копируем свежий код на сервер
2. не трогаем серверные данные и секреты
3. пересобираем контейнер `telegram-helper`
4. проверяем логи после запуска

Важно: этот файл описывает **редеплой TelegramSimple-бота**, а не переустановку host-сервиса `mtproto-proxy`. Если `MTProto` уже работает на Debian-хосте, при обычном редеплое его не удаляем и не переустанавливаем.

---

## Что нельзя затирать

Эти файлы на сервере нужно сохранять:

- `.env`
- `app_keys.json`
- `users.json`
- `vless_config.json`
- `hysteria2_config.json`
- `mtproto_config.json`
- `headscale_config.json`
- `bot.log`

Именно поэтому при загрузке кода ниже используются `exclude`.

---

## Шаг 1. Подключиться к серверу

На macOS / Linux:

```bash
ssh -p 22542 root@138.124.71.73
```

Если видите ошибку `REMOTE HOST IDENTIFICATION HAS CHANGED`, сначала удалите старую запись ключа:

```bash
ssh-keygen -R "[138.124.71.73]:22542"
```

Потом подключитесь снова:

```bash
ssh -p 22542 root@138.124.71.73
```

---

## Шаг 2. Мягко очистить лишние файлы на сервере

Выполнять на сервере:

```bash
cd /opt/TelegramSimple
ls -la | cat
rm -rf .pytest_cache __pycache__ .DS_Store .env.deploy
```

Если хочешь дополнительно почистить Docker-кэш:

```bash
docker builder prune -af
docker image prune -af
docker container prune -f
```

Это не обязательно при каждом обновлении, но полезно, если на сервере мало места.

---

## Шаг 3. Проверить, что `.env` не сломан

Выполнять на сервере:

```bash
ls -ld /opt/TelegramSimple/.env | cat
```

Должен быть обычный файл.

Если вдруг `.env` стал директорией, исправление такое:

```bash
cd /opt/TelegramSimple
docker compose down
rm -rf .env
```

Потом залей `.env` заново:

```bash
scp -P 22542 .env.deploy root@138.124.71.73:/opt/TelegramSimple/.env
```

---

## Шаг 4. Залить свежий проект

### Вариант A. Windows 11 + Git Bash

Открой `Git Bash` и выполни **одной строкой**:

```bash
cd /c/Project/TelegramSimple && tar --exclude='venv' --exclude='.venv' --exclude='__pycache__' --exclude='.env' --exclude='.env.deploy' --exclude='app_keys.json' --exclude='users.json' --exclude='*.log' --exclude='.git' -czf - . | ssh -p 22542 root@138.124.71.73 "cd /opt/TelegramSimple && tar -xzf -"
```

Важно:

- это команда именно для `Git Bash`, не для `PowerShell`
- в `PowerShell` переносы через `\` не работают
- если команда зависла или была вставлена частями, нажми `Ctrl+C` и запусти заново одной строкой в `Git Bash`

### Вариант B. macOS / Linux

Выполнять локально:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramSimple"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.env' \
  --exclude '.env.deploy' \
  --exclude 'app_keys.json' \
  --exclude 'users.json' \
  --exclude '*.log' \
  --exclude '.git' \
  ./ root@138.124.71.73:/opt/TelegramSimple/
```

Важно:

- `requirements.txt` копируется на сервер
- если в проекте добавились новые Python-зависимости, контейнер подтянет их только после `docker compose up --build`
- при обычном редеплое не затирайте `.env`, `app_keys.json`, `users.json`, `mtproto_config.json`

---

## Шаг 5. Пересобрать и запустить бота

Выполнять на сервере:

```bash
cd /opt/TelegramSimple
docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 100 | cat
```

Если всё хорошо, в логах не должно быть повторяющихся traceback-ошибок.

Если у тебя уже есть рабочий `MTProto` на хосте, на этом шаге ничего отдельно для `mtproto-proxy` делать не нужно: редеплой касается только контейнера `telegram-helper-lite`.

Исключение:

- если во время работы через бота менялись `MTProto` клиенты или параметры, которые влияют на `systemd unit`, после редеплоя синхронизируй host service отдельно:

```bash
ssh -p 22542 root@138.124.71.73
cd /opt/TelegramSimple
python3 scripts/mtproto_sync_systemd.py
systemctl show -p ExecStart mtproto-proxy --no-pager | cat
```

---

## Шаг 6. Быстрая проверка после редеплоя

Выполнять на сервере:

```bash
docker ps | cat
docker logs telegram-helper-lite --tail 50 | cat
```

Если нужно проверить, что новая зависимость установилась внутри контейнера:

```bash
docker exec telegram-helper-lite python -c "import qrcode; print('qrcode ok')" | cat
```

Ожидаемый результат:

```text
qrcode ok
```

---

## Частый сценарий именно для QR

Если после обновления бот пишет:

```text
Библиотека qrcode не установлена. Обновите зависимости проекта
```

значит почти всегда произошло одно из двух:

1. на сервер не попал свежий `requirements.txt`
2. контейнер был запущен без пересборки

Правильное исправление:

1. заново выполнить загрузку проекта (`tar + ssh` в Git Bash или `rsync` на macOS/Linux)
2. на сервере выполнить `docker compose up -d --build telegram-helper`
3. проверить `docker exec telegram-helper-lite python -c "import qrcode; print('qrcode ok')" | cat`

---

## Самый короткий сценарий

Если всё уже в порядке и нужна просто обычная доставка новой версии:

На Windows 11 в `Git Bash`:

```bash
cd /c/Project/TelegramSimple && tar --exclude='venv' --exclude='.venv' --exclude='__pycache__' --exclude='.env' --exclude='.env.deploy' --exclude='app_keys.json' --exclude='users.json' --exclude='*.log' --exclude='.git' -czf - . | ssh -p 22542 root@138.124.71.73 "cd /opt/TelegramSimple && tar -xzf -"
```

На macOS / Linux:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramSimple"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' --exclude '.venv' --exclude '__pycache__' \
  --exclude '.env' --exclude '.env.deploy' \
  --exclude 'app_keys.json' --exclude 'users.json' --exclude '*.log' \
  --exclude '.git' \
  ./ root@138.124.71.73:/opt/TelegramSimple/
```

На сервере:

```bash
ssh -p 22542 root@138.124.71.73
cd /opt/TelegramSimple
docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 100 | cat
```

Если после такого редеплоя нужно уже работать с MTProto, используй `MTPROTO_CHEATSHEET.md`: обычный редеплой кода и управление host `mtproto-proxy` это разные сценарии.

---

## Когда нужен не редеплой, а полный cleanup

`CLEANUP_SERVER.md` нужен не для обычного обновления, а когда:

- сервер сильно захламлён
- сломаны директории проекта
- перепутаны файлы `.env`, конфиги или volume-монтирования
- нужно почти с нуля привести проект на сервере в порядок

Для обычного обновления кода используй именно этот файл: `Redeploy TelegramOnly.md`.

Если сервер не сломан, но в `/opt/TelegramSimple` накопились лишние dev/doc/cache-файлы, используй отдельную инструкцию: `Чистка лишних файлов на сервере.md`.
