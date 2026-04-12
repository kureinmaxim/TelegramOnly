# Server Cleanup

Эта инструкция нужна не для полного сброса сервера, а именно для удаления лишних файлов проекта в `/opt/TelegramSimple`, чтобы они не захламляли сервер и не мешали обычному редеплою.

Подходит для сервера:

- `root@138.124.71.73`
- SSH-порт `22542`
- путь проекта `/opt/TelegramSimple`

---

## Что обязательно сохранить

Перед любой чисткой не удаляй:

- `.env`
- `app_keys.json`
- `users.json`
- `vless_config.json`
- `hysteria2_config.json`
- `mtproto_config.json`
- `headscale_config.json`
- `bot.log`
- `compose.yaml`
- `Dockerfile`
- `requirements.txt`
- Python-файлы проекта: `main.py`, `bot.py`, `handlers.py`, `*_manager.py`, `api.py`, `config.py`, `storage.py`, `utils.py`, `security.py`, `encryption.py`

---

## Когда это нужно

Используй эту инструкцию, если на сервере появились:

- случайные мусорные файлы вроде `__pycache_ и. ]_`
- локальные кэши `__pycache__`, `.pytest_cache`
- редакторные и служебные файлы
- документация и тесты, которые не нужны для запуска бота

---

## Шаг 1. Посмотреть, что лежит на сервере

На сервере:

```bash
ssh -p 22542 root@138.124.71.73
cd /opt/TelegramSimple
ls -la | cat
```

---

## Шаг 2. Безопасная чистка мусора

Этот вариант удаляет только явный мусор и случайные файлы. Он безопасен для обычного рабочего сервера.

На сервере:

```bash
cd /opt/TelegramSimple
rm -rf -- \
  "__pycache_ и. ]_" \
  __pycache__ \
  .pytest_cache \
  .mypy_cache \
  .ruff_cache \
  .cache \
  venv \
  .venv \
  .git \
  .cursor \
  .vscode \
  .idea

rm -f -- \
  .DS_Store \
  .env.deploy \
  *.swp \
  *.swo

ls -la | cat
```

---

## Шаг 3. Умеренная чистка dev/doc-файлов

Этот вариант подходит, если сервер нужен только для запуска бота, а документация, тесты и workspace-файлы там не нужны.

На сервере:

```bash
cd /opt/TelegramSimple
rm -rf -- tests docs
rm -f -- *.md *.code-workspace
ls -la | cat
```

После этого на сервере останется в основном только то, что реально нужно для сборки и запуска контейнера.

---

## Что можно удалить именно из твоего текущего списка

По твоему `ls` можно смело убрать как лишнее:

- `__pycache__`
- `__pycache_ и. ]_`
- `AGENTS.md`
- `CLAUDE.md`
- `*.md` файлы с гайдами
- `ApiAi.code-workspace`
- `tests`
- `docs`

Обычно не трогаем:

- `compose.yaml`
- `Dockerfile`
- `requirements.txt`
- `pyproject.toml`
- `main.py`
- `bot.py`
- `handlers.py`
- `*_manager.py`
- `web`
- `scripts`
- `dockhand`

Последние три каталога можно удалить только если ты точно не используешь их в своём сценарии.

---

## Как не загрязнять сервер снова

Главное правило: не копировать на сервер всё подряд.

Для следующего редеплоя используй `rsync` с расширенным списком исключений.

На Mac:

```bash
cd "/Users/olgazaharova/Project/ProjectPython/TelegramSimple"
rsync -avz -e 'ssh -p 22542' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude '.git' \
  --exclude '.cursor' \
  --exclude '.vscode' \
  --exclude '.idea' \
  --exclude '.env' \
  --exclude '.env.deploy' \
  --exclude 'tests/' \
  --exclude 'docs/' \
  --exclude '*.md' \
  --exclude '*.code-workspace' \
  --exclude 'app_keys.json' \
  --exclude 'users.json' \
  --exclude '*.log' \
  ./ root@138.124.71.73:/opt/TelegramSimple/
```

---

## Почему не стоит использовать `rsync --delete`

Для этого проекта лучше не делать слепой `--delete`, потому что на сервере есть важные локальные файлы, которых нет в git:

- `.env`
- `app_keys.json`
- `users.json`
- конфиги протоколов
- `bot.log`

Неосторожный `--delete` может снести нужные данные.

---

## Быстрая проверка после чистки

На сервере:

```bash
cd /opt/TelegramSimple
docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 50 | cat
docker exec telegram-helper-lite python -c "import qrcode; print('qrcode ok')" | cat
```

Если видишь `qrcode ok`, контейнер живой и редеплой после чистки прошёл нормально.

---

## Короткий рабочий сценарий

Если хочешь просто быстро привести директорию в порядок:

На сервере:

```bash
ssh -p 22542 root@138.124.71.73
cd /opt/TelegramSimple
rm -rf -- "__pycache_ и. ]_" __pycache__ .pytest_cache .mypy_cache .ruff_cache .cache .git .cursor .vscode .idea venv .venv
rm -f -- .DS_Store .env.deploy *.swp *.swo
rm -rf -- tests docs
rm -f -- *.md *.code-workspace
ls -la | cat
docker compose up -d --build telegram-helper
docker logs telegram-helper-lite --tail 50 | cat
```

Если нужна только мягкая чистка без удаления документации, выполняй только блок `Безопасная чистка мусора`.
