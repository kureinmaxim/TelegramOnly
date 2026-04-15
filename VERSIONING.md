# Управление версиями и метаданными

В этом документе описан процесс версионирования проекта `TelegramSimple`. Мы используем [Semantic Versioning](https://semver.org/) и автоматизированные скрипты для управления версиями.

---

## 🚀 Quick Start

**macOS / Linux:**
```bash
python3 scripts/bump_version.py              # Проверить версии
python3 scripts/bump_version.py --sync       # Синхронизировать файлы
python3 scripts/bump_version.py --bump patch # Bump 1.2.3 → 1.2.4
```

**Windows (PowerShell):**
```powershell
python scripts/bump_version.py              # Проверить версии
python scripts/bump_version.py --sync       # Синхронизировать файлы
python scripts/bump_version.py --bump patch # Bump 1.2.3 → 1.2.4
```

**Пример вывода:**
```
==================================================
📦 TelegramSimple — Version Summary
==================================================

🏷️  pyproject.toml (source of truth)
   Version:      3.4.5
   Release date: 24.12.2025

📁 Other files:
   ✅ OK api.py (3.4.5) — FastAPI version

--------------------------------------------------
✅ All version references are in sync!
```

---

## 1. Источник правды

Вся информация о версии и метаданных хранится в файле `pyproject.toml`. Это единственный файл, который нужно менять (или который меняет скрипт).

Ключевые поля в `pyproject.toml`:
*   `[project].version` — Текущая версия (например, `1.2.3`)
*   `[tool.telegramhelper.metadata].release_date` — Дата релиза (формат `DD.MM.YYYY`)
*   `[tool.telegramhelper.metadata].last_updated` — Дата последнего изменения (формат `YYYY-MM-DD`)
*   `[tool.telegramhelper.metadata].developer` — Имя разработчика

---

## 2. Схема версионирования

Мы используем формат **MAJOR.MINOR.PATCH** (например, `1.5.2`):

*   **MAJOR** (Мажорная): Критические изменения, ломающие обратную совместимость.
*   **MINOR** (Минорная): Новые функции, сохраняющие обратную совместимость.
*   **PATCH** (Патч): Исправление ошибок без добавления функционала.

---

## 3. Инструмент обновления (bump_version.py)

Для управления версиями используется скрипт `scripts/bump_version.py`. Он автоматически обновляет версию и даты в `pyproject.toml`.

### Основные команды

#### 🐛 Выпуск исправления (Patch)
Используйте, когда исправили баг.

**Windows (PowerShell):**
```powershell
python scripts/bump_version.py --bump patch
# Результат: 1.2.3 -> 1.2.4 (дата релиза обновляется на сегодня)
```

**macOS / Linux (Bash):**
```bash
./scripts/bump_version.py --bump patch
# Результат: 1.2.3 -> 1.2.4
```

#### ✨ Новая функциональность (Minor)
Используйте, когда добавили новую фичу.

**Windows (PowerShell):**
```powershell
python scripts/bump_version.py --bump minor
# Результат: 1.2.3 -> 1.3.0
```

**macOS / Linux (Bash):**
```bash
./scripts/bump_version.py --bump minor
# Результат: 1.2.3 -> 1.3.0
```

#### 💥 Критические изменения (Major)
Используйте при глобальных изменениях.

**Windows (PowerShell):**
```powershell
python scripts/bump_version.py --bump major
# Результат: 1.2.3 -> 2.0.0
```

**macOS / Linux (Bash):**
```bash
./scripts/bump_version.py --bump major
# Результат: 1.2.3 -> 2.0.0
```

---

## 4. Продвинутое использование

### Установка конкретной версии
Если нужно установить версию вручную:

**Windows (PowerShell):**
```powershell
python scripts/bump_version.py --version 2.0.0
```

**macOS / Linux (Bash):**
```bash
./scripts/bump_version.py --version 2.0.0
```

### Управление датами
По умолчанию скрипт обновляет `release_date` и `last_updated` на сегодняшнюю дату.

**Не обновлять дату релиза (только версию):**
```bash
# PowerShell
python scripts/bump_version.py --bump patch --no-release-date

# Bash
./scripts/bump_version.py --bump patch --no-release-date
```

**Установить конкретную дату релиза:**
```bash
# PowerShell
python scripts/bump_version.py --version 1.5.0 --release-date 31.12.2025

# Bash
./scripts/bump_version.py --version 1.5.0 --release-date 31.12.2025
```

### Смена разработчика
Если над проектом начал работать другой человек:
```bash
# PowerShell
python scripts/bump_version.py --developer "Иванов И.И."

# Bash
./scripts/bump_version.py --developer "Иванов И.И."
```

---

## 5. Чек-лист релиза

1.  Убедитесь, что все тесты проходят.
2.  Запустите скрипт обновления версии:
    ```bash
    ./scripts/bump_version.py --bump minor
    ```
3.  Проверьте изменения в `pyproject.toml`.
4.  Сделайте коммит изменений:
    ```bash
    git add pyproject.toml
    git commit -m "Bump version to 1.3.0"
    ```
5.  Создайте тег (опционально):
    ```bash
    git tag v1.3.0
    ```

---

## 6. Деплой на сервер

После изменения версии нужно синхронизировать код на сервер и перезапустить бота.

### Windows (PowerShell)

**Вариант 1: SCP с robocopy (рекомендуется)**

```powershell
# Создать временную папку и синхронизовать
$sourceDir = "C:\Project\TelegramSimple"
$tempDir = "$env:TEMP\TelegramSimple_sync"
$server = "root@YOUR_SERVER_IP"
$serverPath = "/opt/TelegramSimple/"
$sshPort = "YOUR_SSH_PORT"

# Копировать файлы локально, исключая ненужные
robocopy $sourceDir $tempDir /E /Z `
  /XD venv __pycache__ .git .pytest_cache `
  /XF bot.log .env app_keys.json users.json vless_config.json *.pyc

# Загрузить на сервер
scp -P $sshPort -r "$tempDir\*" "${server}:${serverPath}"

# Очистить временную папку
Remove-Item -Recurse -Force $tempDir

# Перезапустить бота
ssh -p $sshPort $server "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper"
```

**Вариант 2: Git (если на сервере настроен git)**

```powershell
# Закоммитить изменения локально
git add pyproject.toml
git commit -m "Bump version to 1.3.0"
git push

# Обновить на сервере
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && git pull && docker compose up -d --build telegram-helper"
```

### macOS / Linux (Bash)

**Вариант 1: rsync (рекомендуется)**

```bash
# Синхронизация одной командой
rsync -av --delete \
  --exclude 'venv/' --exclude '__pycache__/' \
  --exclude '.git/' --exclude 'bot.log' \
  --exclude '.env' --exclude 'app_keys.json' \
  --exclude 'users.json' --exclude 'vless_config.json' \
  -e 'ssh -p YOUR_SSH_PORT' \
  /path/to/TelegramSimple/ \
  root@YOUR_SERVER_IP:/opt/TelegramSimple/

# Перезапустить бота
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper"
```

**Вариант 2: Всё в одну команду**

```bash
rsync -av --delete --exclude 'venv/' --exclude '__pycache__/' --exclude '.git/' --exclude 'bot.log' --exclude '.env' --exclude 'app_keys.json' --exclude 'users.json' --exclude 'vless_config.json' -e 'ssh -p YOUR_SSH_PORT' /path/to/TelegramSimple/ root@YOUR_SERVER_IP:/opt/TelegramSimple/ && ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper"
```

**Вариант 3: Git**

```bash
# Закоммитить и отправить
git add pyproject.toml
git commit -m "Bump version to 1.3.0"
git push

# Обновить на сервере
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && git pull && docker compose up -d --build telegram-helper"
```

---

## 7. Проверка версии на сервере

Для проверки версии проекта на сервере используется скрипт `scripts/show_version.py`:

### Быстрая проверка

```bash
python3 scripts/show_version.py
```

### Вывод скрипта

```
============================================================
📦 Информация о версии TelegramSimple
============================================================

🏷️  Версия: 3.1.1
📁 Путь: /opt/TelegramSimple
🐳 Docker: Нет (хост-система)

------------------------------------------------------------
📊 Git информация:
------------------------------------------------------------
🌿 Ветка: feature/simplified-vless-bot
🔖 Коммит: 85be5c7
📅 Дата: 2025-01-15 12:30:00
💬 Сообщение: feat: add show_version.py script...
✅ Рабочая директория чистая

------------------------------------------------------------
🔐 Разрешённые приложения (ALLOWED_APPS):
------------------------------------------------------------
  • bomcategorizer-v5
  • apiai-v3
  • test-client

------------------------------------------------------------
🐍 Python информация:
------------------------------------------------------------
  Версия: 3.11.x
  Путь: /usr/bin/python3
```

### Что показывает скрипт

| Информация | Описание |
|------------|----------|
| 🏷️ **Версия** | Из `pyproject.toml` |
| 📁 **Путь** | Расположение проекта |
| 🐳 **Docker** | Запущен ли в контейнере |
| 🌿 **Git ветка** | Текущая ветка |
| 🔖 **Коммит** | Короткий хеш последнего коммита |
| 📅 **Дата** | Дата последнего коммита |
| 🔐 **ALLOWED_APPS** | Список разрешённых приложений из `security.py` |

### Использование

```bash
# На сервере после деплоя
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP
cd /opt/TelegramSimple
python3 scripts/show_version.py
```

Это позволяет быстро убедиться, что на сервере развёрнута правильная версия кода.

Чтобы версия в боте (`/ver`) совпадала с `pyproject.toml` после bump, на сервер нужно доставить файлы и **пересобрать** контейнер (`docker compose up -d --build`), а не только `restart`. Пошаговый чеклист — в **`REDEPLOY.md`**. Путь на сервере: для **новых** установок целевой каталог **`/opt/TelegramOnly`**; на **legacy** VPS часто **`/opt/TelegramSimple`** — везде один и тот же путь, что в примерах ниже по этому файлу, замените на свой.

---

## 8. Синхронизация и проверка версии (одной командой)

Для полного цикла деплоя с автоматической проверкой версии.

### macOS / Linux (Bash)

**Полная синхронизация + проверка:**

```bash
# Sync + Verify
rsync -av --delete \
  --exclude 'venv/' --exclude '__pycache__/' \
  --exclude '.git/' --exclude 'bot.log' \
  --exclude '.env' --exclude 'app_keys.json' \
  --exclude 'users.json' --exclude 'vless_config.json' \
  -e 'ssh -p YOUR_SSH_PORT' \
  /path/to/TelegramSimple/ \
  root@YOUR_SERVER_IP:/opt/TelegramSimple/ \
  && ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper && sleep 2 && python3 scripts/show_version.py"
```

**Алиас для быстрого использования (добавьте в `~/.zshrc` или `~/.bashrc`):**

```bash
alias deploy-ts='rsync -av --delete --exclude "venv/" --exclude "__pycache__/" --exclude ".git/" --exclude "bot.log" --exclude ".env" --exclude "app_keys.json" --exclude "users.json" --exclude "vless_config.json" -e "ssh -p YOUR_SSH_PORT" /path/to/TelegramSimple/ root@YOUR_SERVER_IP:/opt/TelegramSimple/ && ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper && sleep 2 && python3 scripts/show_version.py"'
```

После добавления алиаса выполните `source ~/.zshrc`, затем используйте:

```bash
deploy-ts
```

### Windows (PowerShell)

**Полная синхронизация + проверка:**

```powershell
# Функция для деплоя
function Deploy-TelegramSimple {
    $sourceDir = "C:\Project\TelegramSimple"
    $tempDir = "$env:TEMP\TelegramSimple_sync"
    $server = "root@YOUR_SERVER_IP"
    $serverPath = "/opt/TelegramSimple/"
    $sshPort = "YOUR_SSH_PORT"
    
    # Синхронизировать
    robocopy $sourceDir $tempDir /E /Z `
      /XD venv __pycache__ .git .pytest_cache `
      /XF bot.log .env app_keys.json users.json vless_config.json *.pyc
    
    scp -P $sshPort -r "$tempDir\*" "${server}:${serverPath}"
    Remove-Item -Recurse -Force $tempDir
    
    # Перезапустить и проверить
    ssh -p $sshPort $server "cd /opt/TelegramSimple && docker compose up -d --build telegram-helper && sleep 2 && python3 scripts/show_version.py"
}

# Использование
Deploy-TelegramSimple
```

### Только проверка версии (без синхронизации)

```bash
# macOS / Linux
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && python3 scripts/show_version.py"
```

```powershell
# Windows
ssh -p YOUR_SSH_PORT root@YOUR_SERVER_IP "cd /opt/TelegramSimple && python3 scripts/show_version.py"
```