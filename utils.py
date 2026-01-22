"""
Вспомогательные функции для безопасности.
"""
import re
import json
import hashlib
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Callable
from urllib.parse import urlparse
from datetime import datetime, timedelta
from security.interfaces import ActionType, SecurityRule

# Кэш для хэшей действий (чтобы не генерировать каждый раз)
_action_hash_cache = {}
_cache_ttl = timedelta(minutes=10)

def detect_action_type(tool_name: str, args: Dict, context: Optional[Dict] = None) -> ActionType:
    """Определить тип действия по названию инструмента и аргументам."""
    from security.interfaces import ActionType
    
    context = context or {}
    
    # Извлекаем значения из args, убеждаясь, что это строки (не корутины)
    def get_arg_value(arg_name: str, default: str = "") -> str:
        value = args.get(arg_name, default)
        # Если значение - корутина, пытаемся получить результат
        if asyncio.iscoroutine(value):
            try:
                # Не можем вызвать await здесь, поэтому возвращаем пустую строку
                return ""
            except:
                return ""
        return str(value) if value is not None else ""
    
    if tool_name == "click_element":
        target = get_arg_value("description", "").lower()
        
        # Определяем подтип клика
        if any(word in target for word in ["купить", "оплатить", "заказ", "buy", "checkout", "cart", "корзин"]):
            return ActionType.PAYMENT
        elif any(word in target for word in ["удалить", "delete", "remove", "отменить", "cancel"]):
            return ActionType.DELETE
        elif any(word in target for word in ["отправить", "подтвердить", "submit", "save", "сохранить", "далее", "продолжить"]):
            return ActionType.FORM_SUBMIT
        elif any(word in target for word in ["пост", "share", "tweet", "comment", "лайк", "like"]):
            return ActionType.SOCIAL_ACTION
        elif any(word in target for word in ["принять", "согласиться", "agree", "terms", "условия"]):
            return ActionType.LEGAL_ACTION
        elif any(word in target for word in ["http", "www", ".com", ".ru", "ссылка", "link"]):
            return ActionType.CLICK_LINK
        else:
            return ActionType.CLICK_BUTTON
    
    elif tool_name == "type_text":
        text = get_arg_value("text", "").lower()
        
        # Определяем тип вводимых данных
        if any(word in text for word in ["пароль", "password", "pwd", "pass", "ключ", "key", "pin"]):
            return ActionType.TYPE_PASSWORD
        elif "@" in text and "." in text and len(text) > 5:
            return ActionType.TYPE_EMAIL
        elif re.search(r'(\+7|8\d{10}|\d{11})', text):
            return ActionType.TYPE_PHONE
        elif re.search(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b', text):
            return ActionType.TYPE_CARD
        elif any(word in text for word in ["паспорт", "фио", "адрес", "город", "страна", "рождение", "снилс", "инн"]):
            return ActionType.TYPE_PERSONAL
        elif context.get("is_login_page", False) and context.get("contains_passwords", False):
            return ActionType.TYPE_PASSWORD
        else:
            return ActionType.TYPE
    
    elif tool_name == "navigate":
        url = get_arg_value("url", "").lower()
        if url.startswith("http://"):
            return ActionType.NAVIGATE_SUSPICIOUS
        elif any(word in url for word in ["phishing", "malware", "scam", ".exe", ".zip", ".rar"]):
            return ActionType.NAVIGATE_SUSPICIOUS
        else:
            return ActionType.NAVIGATE
    
    elif tool_name == "scroll_down":
        return ActionType.SCROLL
    
    elif tool_name == "analyze_page":
        return ActionType.ANALYZE
    
    else:
        return ActionType.CLICK

def is_external_domain(current_url: str, target_url: str) -> bool:
    """Проверить, является ли домен внешним."""
    try:
        current_domain = urlparse(current_url).netloc
        target_domain = urlparse(target_url).netloc
        if not current_domain or not target_domain:
            return False
        return target_domain != current_domain
    except Exception:
        return False

def mask_sensitive_data(text: str) -> str:
    """Замаскировать чувствительные данные в тексте."""
    if not text:
        return text
    
    # Проверяем, что text - это строка, а не корутина
    if asyncio.iscoroutine(text):
        return "[coroutine]"
    
    # Номера карт
    text = re.sub(
        r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        lambda m: f'{m.group()[:4]} **** **** {m.group()[-4:]}',
        text
    )
    
    # CVV/CVC
    text = re.sub(
        r'\b(CVV|CVC)[:\s]*\d{3,4}\b',
        r'\1: ***',
        text,
        flags=re.IGNORECASE
    )
    
    # Пароли (в логах)
    if "пароль" in text.lower() or "password" in text.lower():
        text = re.sub(
            r'(пароль|password)[:\s]*[^\s]+',
            r'\1: *******',
            text,
            flags=re.IGNORECASE
        )
    
    # Email частично
    text = re.sub(
        r'\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Z|a-z]{2,})\b',
        lambda m: f'{m.group(1)[:3]}***@{m.group(2)}',
        text
    )
    
    # Телефоны
    text = re.sub(
        r'\b(\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b',
        lambda m: f'{m.group()[:4]} *** ** {m.group()[-2:]}',
        text
    )
    
    return text

def generate_action_hash(action_type: ActionType, target: str, context: Dict[str, Any]) -> str:
    """Генерация уникального хеша для действия."""
    cache_key = f"{action_type.value}:{target}:{context.get('current_url', '')}"
    
    # Проверяем кэш
    if cache_key in _action_hash_cache:
        cached_data = _action_hash_cache[cache_key]
        if datetime.now() - cached_data['timestamp'] < _cache_ttl:
            return cached_data['hash']
    
    # Генерируем новый хеш
    data = f"{action_type.value}:{target}:{context.get('current_url', '')}:{hashlib.md5(json.dumps(context, sort_keys=True).encode()).hexdigest()[:8]}"
    action_hash = hashlib.md5(data.encode()).hexdigest()[:16]
    
    # Сохраняем в кэш
    _action_hash_cache[cache_key] = {
        'hash': action_hash,
        'timestamp': datetime.now()
    }
    
    # Очищаем старые записи
    _clean_hash_cache()
    
    return action_hash

def _clean_hash_cache():
    """Очистить старые записи из кэша хешей."""
    global _action_hash_cache
    now = datetime.now()
    to_remove = []
    
    for key, data in _action_hash_cache.items():
        if now - data['timestamp'] > _cache_ttl:
            to_remove.append(key)
    
    for key in to_remove:
        del _action_hash_cache[key]

def extract_domain(url: str) -> str:
    """Извлечь домен из URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return ""

def is_suspicious_domain(domain: str) -> bool:
    """Проверить, является ли домен подозрительным."""
    suspicious_tlds = ['.tk', '.ml', '.ga', '.cf', '.gq', '.xyz', '.top', '.club']
    suspicious_keywords = ['phishing', 'malware', 'scam', 'hack', 'exploit']
    
    domain_lower = domain.lower()
    
    # Проверяем TLD
    for tld in suspicious_tlds:
        if domain_lower.endswith(tld):
            return True
    
    # Проверяем ключевые слова
    for keyword in suspicious_keywords:
        if keyword in domain_lower:
            return True
    
    return False

def normalize_text(text: str) -> str:
    """Нормализовать текст для сравнения."""
    if not text:
        return ""
    
    # Проверяем, не корутина ли
    if asyncio.iscoroutine(text):
        return ""
    
    # Приводим к нижнему регистру
    text = text.lower()
    
    # Удаляем лишние пробелы
    text = ' '.join(text.split())
    
    # Удаляем специальные символы (оставляем только буквы, цифры и пробелы)
    text = re.sub(r'[^a-zа-яё0-9\s]', ' ', text)
    
    return text.strip()

def calculate_text_similarity(text1: str, text2: str) -> float:
    """Вычислить схожесть двух текстов."""
    if not text1 or not text2:
        return 0.0
    
    # Нормализуем тексты
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Простой алгоритм схожести (можно заменить на более сложный)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union) if union else 0.0

async def safe_execute(func: Callable, *args, **kwargs) -> Tuple[bool, Any]:
    """Безопасно выполнить функцию с обработкой исключений."""
    try:
        result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
        return True, result
    except Exception as e:
        return False, str(e)