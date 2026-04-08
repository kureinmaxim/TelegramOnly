#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест совместимости шифрования между BOMCategorizer и TelegramSimple.
Этот скрипт имитирует отправку запроса из BOMCategorizer.
"""

import sys
import os
from pathlib import Path

# Добавляем путь к модулю encryption из BOMCategorizer
project_root = Path(__file__).resolve().parents[1]
bom_path = Path(os.environ.get("BOMCATEGORIZER_PATH", project_root.parent / "BOMCategorizer"))
sys.path.insert(0, str(bom_path))

from bom_categorizer.encryption import SecureMessenger as BOMSecureMessenger

# Добавляем путь к модулю encryption из TelegramOnly
telegram_path = project_root
sys.path.insert(0, str(telegram_path))

from encryption import SecureMessenger as TelegramSecureMessenger

import json
import base64

def test_cross_compatibility():
    """Тест кросс-совместимости шифрования"""
    
    print("=" * 70)
    print("🔄 Тест совместимости шифрования BOMCategorizer ↔ TelegramSimple")
    print("=" * 70)
    
    # Один ключ для обоих модулей
    test_key = "a" * 64  # 256-bit hex key
    
    # Тестовые данные (как в BOMCategorizer)
    test_data = {
        "prompt": "Классифицируй компонент: Резистор С2-23",
        "provider": "anthropic",
        "max_tokens": 1000
    }
    
    print(f"\n📦 Тестовые данные:")
    print(f"   {json.dumps(test_data, ensure_ascii=False)}")
    
    # === ТЕСТ 1: BOMCategorizer -> TelegramSimple ===
    print(f"\n" + "─" * 70)
    print("1️⃣ Тест: BOMCategorizer шифрует → TelegramSimple расшифровывает")
    print("─" * 70)
    
    try:
        # Инициализация
        bom_messenger = BOMSecureMessenger(test_key)
        telegram_messenger = TelegramSecureMessenger(test_key)
        
        # Шифруем в BOMCategorizer
        encrypted_by_bom = bom_messenger.encrypt(test_data)
        print(f"   ✓ BOMCategorizer зашифровал: {len(encrypted_by_bom)} байт")
        print(f"   ✓ Формат: nonce({encrypted_by_bom[:12].hex()[:20]}...) + ciphertext")
        
        # Расшифровываем в TelegramSimple
        decrypted_by_telegram = telegram_messenger.decrypt(encrypted_by_bom)
        result = json.loads(decrypted_by_telegram.decode('utf-8'))
        print(f"   ✓ TelegramSimple расшифровал: {json.dumps(result, ensure_ascii=False)}")
        
        if result == test_data:
            print(f"   ✅ УСПЕХ: Данные совпадают!")
        else:
            print(f"   ❌ ОШИБКА: Данные не совпадают!")
            return False
            
    except Exception as e:
        print(f"   ❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # === ТЕСТ 2: TelegramSimple -> BOMCategorizer ===
    print(f"\n" + "─" * 70)
    print("2️⃣ Тест: TelegramSimple шифрует → BOMCategorizer расшифровывает")
    print("─" * 70)
    
    try:
        # Тестовый ответ от API
        response_data = {
            "response": "Категория: resistors, Уверенность: high",
            "provider": "anthropic",
            "status": "success"
        }
        
        # Шифруем в TelegramSimple
        encrypted_by_telegram = telegram_messenger.encrypt(response_data)
        print(f"   ✓ TelegramSimple зашифровал: {len(encrypted_by_telegram)} байт")
        
        # Расшифровываем в BOMCategorizer
        decrypted_by_bom = bom_messenger.decrypt(encrypted_by_telegram)
        result = json.loads(decrypted_by_bom.decode('utf-8'))
        print(f"   ✓ BOMCategorizer расшифровал: {json.dumps(result, ensure_ascii=False)[:60]}...")
        
        if result == response_data:
            print(f"   ✅ УСПЕХ: Данные совпадают!")
        else:
            print(f"   ❌ ОШИБКА: Данные не совпадают!")
            return False
            
    except Exception as e:
        print(f"   ❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # === ТЕСТ 3: Base64 формат (как в API) ===
    print(f"\n" + "─" * 70)
    print("3️⃣ Тест: Base64 формат (полный цикл через API)")
    print("─" * 70)
    
    try:
        # BOMCategorizer шифрует и кодирует в Base64
        encrypted = bom_messenger.encrypt(test_data)
        b64_request = base64.b64encode(encrypted).decode('utf-8')
        print(f"   ✓ BOMCategorizer отправляет: {b64_request[:50]}...")
        
        # TelegramSimple получает и расшифровывает
        received = base64.b64decode(b64_request)
        decrypted = telegram_messenger.decrypt(received)
        parsed = json.loads(decrypted.decode('utf-8'))
        print(f"   ✓ TelegramSimple получил: {json.dumps(parsed, ensure_ascii=False)[:50]}...")
        
        # TelegramSimple шифрует ответ и кодирует в Base64
        encrypted_response = telegram_messenger.encrypt(response_data)
        b64_response = base64.b64encode(encrypted_response).decode('utf-8')
        print(f"   ✓ TelegramSimple отправляет: {b64_response[:50]}...")
        
        # BOMCategorizer получает и расшифровывает
        received_response = base64.b64decode(b64_response)
        decrypted_response = bom_messenger.decrypt(received_response)
        final_result = json.loads(decrypted_response.decode('utf-8'))
        print(f"   ✓ BOMCategorizer получил: {json.dumps(final_result, ensure_ascii=False)[:50]}...")
        
        if final_result == response_data:
            print(f"   ✅ УСПЕХ: Полный цикл работает!")
        else:
            print(f"   ❌ ОШИБКА: Данные не совпадают после полного цикла!")
            return False
            
    except Exception as e:
        print(f"   ❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print(f"\n" + "=" * 70)
    print("✨ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("🎯 Шифрование полностью совместимо между проектами")
    print("=" * 70)
    
    return True

if __name__ == "__main__":
    success = test_cross_compatibility()
    sys.exit(0 if success else 1)
