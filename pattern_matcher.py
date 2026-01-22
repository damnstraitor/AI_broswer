"""
Поиск паттернов в тексте.
"""
import re
from typing import Dict, Any, List, Optional
from security.interfaces import IPatternMatcher
from security.utils import mask_sensitive_data

class PatternMatcher(IPatternMatcher):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.patterns = self._load_patterns()
    
    def _load_patterns(self) -> Dict[str, Dict[str, str]]:
        """Загрузить паттерны для анализа."""
        return {
            "personal_data": {
                "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                "phone_ru": r'\b(\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b',
                "phone_international": r'\b\+\d{1,3}[\s-]?\d{1,14}\b',
                "passport": r'\b\d{4}[- ]?\d{6}\b',
                "inn": r'\b\d{10,12}\b',
                "snils": r'\b\d{3}-\d{3}-\d{3} \d{2}\b',
                "name": r'\b(?:[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b',
                "address": r'\b(?:ул\.|улица|пр\.|проспект|пер\.|переулок|д\.|дом|кв\.|квартира)\b.*?\b\d+\b',
            },
            "financial_data": {
                "card_number": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b',
                "cvv": r'\b\d{3,4}\b',
                "expiry_date": r'\b(0[1-9]|1[0-2])[/-](2[0-9]|3[0-9])\b',
                "iban": r'\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b',
                "swift": r'\b[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?\b',
                "bank_account": r'\b\d{20}\b',
                "amount": r'\b\d+[.,]\d{2}\s*(?:руб|р|usd|eur|€|$)\b',
            },
            "sensitive_keywords": {
                "password": r'\b(пароль|password|pwd|pass|ключ|key|pin|код.*доступ|secret.*key)\b',
                "secret": r'\b(секрет|secret|confidential|private|приватный|конфиденциальный)\b',
                "security": r'\b(безопасность|security|auth|token|api.?key|access.*token)\b',
                "login": r'\b(логин|login|username|user.*name|account.*name)\b',
                "authorization": r'\b(авторизация|authorization|авторизоваться|authenticate)\b',
            },
            "url_patterns": {
                "http": r'http://[^\s]+',
                "https": r'https://[^\s]+',
                "ip_address": r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
                "local_path": r'[A-Za-z]:\\[^\\].*|\/[^\/].*',
            },
            "dangerous_patterns": {
                "javascript": r'javascript:|<\s*script\s*>|eval\(|alert\(|document\.cookie',
                "sql_injection": r'\b(?:union\s+select|select\s+.*\s+from|insert\s+into|delete\s+from|drop\s+table)\b',
                "xss": r'<\s*(?:script|iframe|object|embed)\s*>|on\w+\s*=',
            }
        }
    
    async def find_patterns(self, text: str, pattern_type: str = "all") -> Dict[str, Dict[str, List[str]]]:
        """Найти паттерны в тексте."""
        results = {}
        
        patterns_to_check = {}
        if pattern_type == "all":
            patterns_to_check = self.patterns
        elif pattern_type in self.patterns:
            patterns_to_check = {pattern_type: self.patterns[pattern_type]}
        else:
            return results
        
        for category, category_patterns in patterns_to_check.items():
            category_results = {}
            for pattern_name, pattern in category_patterns.items():
                try:
                    matches = re.findall(pattern, text, re.IGNORECASE | re.UNICODE)
                    if matches:
                        # Преобразуем в список строк (findall может возвращать tuple)
                        matches_list = []
                        for match in matches:
                            if isinstance(match, tuple):
                                matches_list.extend([m for m in match if m])
                            elif match:
                                matches_list.append(str(match))
                        
                        if matches_list:
                            category_results[pattern_name] = matches_list
                except Exception as e:
                    print(f"Ошибка при поиске паттерна {pattern_name}: {e}")
                    continue
            
            if category_results:
                results[category] = category_results
        
        return results
    
    async def extract_sensitive_data(self, text: str) -> Dict[str, Any]:
        """Извлечь чувствительные данные с контекстом."""
        results = await self.find_patterns(text, "all")
        
        # Статистика найденных паттернов
        stats = {
            "total_patterns": sum(len(matches) for category in results.values() 
                                for matches in category.values()),
            "has_personal_data": "personal_data" in results,
            "has_financial_data": "financial_data" in results,
            "has_sensitive_keywords": "sensitive_keywords" in results,
            "has_dangerous_patterns": "dangerous_patterns" in results,
        }
        
        # Анализ контекста
        context_analysis = {
            "contains_passwords": False,
            "contains_financial": False,
            "contains_contact_info": False,
            "contains_personal_data": False,
            "contains_dangerous": False,
            "confidence": 0.0,
        }
        
        # Анализ ключевых слов
        if "sensitive_keywords" in results:
            keywords = results["sensitive_keywords"]
            if "password" in keywords:
                context_analysis["contains_passwords"] = True
        
        # Анализ финансовых данных
        if "financial_data" in results:
            context_analysis["contains_financial"] = True
        
        # Анализ персональных данных
        if "personal_data" in results:
            personal = results["personal_data"]
            if "email" in personal or "phone_ru" in personal or "phone_international" in personal:
                context_analysis["contains_contact_info"] = True
            context_analysis["contains_personal_data"] = True
        
        # Опасные паттерны
        if "dangerous_patterns" in results:
            context_analysis["contains_dangerous"] = True
        
        # Рассчитываем уверенность
        confidence_factors = []
        
        if context_analysis["contains_passwords"]:
            confidence_factors.append(0.9)
        
        if context_analysis["contains_financial"]:
            confidence_factors.append(0.8)
        
        if context_analysis["contains_dangerous"]:
            confidence_factors.append(0.95)
        
        if stats["total_patterns"] > 0:
            confidence_factors.append(min(stats["total_patterns"] * 0.2, 1.0))
        
        context_analysis["confidence"] = (
            sum(confidence_factors) / len(confidence_factors) 
            if confidence_factors else 0.0
        )
        
        # Маскируем текст для логирования
        masked_text = mask_sensitive_data(text)
        
        # Метаданные
        metadata = {
            "text_length": len(text),
            "word_count": len(text.split()),
            "has_urls": "url_patterns" in results,
            "extraction_time": "timestamp",
        }
        
        return {
            "patterns": results,
            "stats": stats,
            "context": context_analysis,
            "masked_text": masked_text,
            "metadata": metadata,
        }
    
    def get_available_patterns(self) -> List[str]:
        """Получить список доступных типов паттернов."""
        return list(self.patterns.keys())
    
    def add_custom_pattern(self, category: str, name: str, pattern: str) -> None:
        """Добавить пользовательский паттерн."""
        if category not in self.patterns:
            self.patterns[category] = {}
        
        self.patterns[category][name] = pattern
    
    def remove_pattern(self, category: str, name: str) -> bool:
        """Удалить паттерн."""
        if category in self.patterns and name in self.patterns[category]:
            del self.patterns[category][name]
            
            # Удаляем пустую категорию
            if not self.patterns[category]:
                del self.patterns[category]
            
            return True
        return False