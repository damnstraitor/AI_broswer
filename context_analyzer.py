"""
Анализ контекста действий.
"""
from typing import Dict, Any, List, Optional
from security.interfaces import IContextAnalyzer, ActionType, IPatternMatcher
from security.utils import is_external_domain, is_suspicious_domain, extract_domain

class ContextAnalyzer(IContextAnalyzer):
    def __init__(self, pattern_matcher: IPatternMatcher):
        self.pattern_matcher = pattern_matcher
        self.keyword_patterns = self._load_keyword_patterns()
        self.domain_categories = self._load_domain_categories()
    
    def _load_keyword_patterns(self) -> Dict[str, List[str]]:
        """Загрузить ключевые слова для анализа."""
        return {
            "payment": ["купить", "оплатить", "цена", "стоимость", "чек", "checkout", "buy", "purchase", "cart", "корзин", "оплат"],
            "login": ["войти", "вход", "логин", "sign in", "log in", "авторизация", "account", "аккаунт"],
            "registration": ["регистрация", "зарегистрироваться", "sign up", "register", "создать аккаунт"],
            "social": ["пост", "публикация", "поделиться", "share", "comment", "комментарий", "like", "лайк", "репост"],
            "delete": ["удалить", "удаление", "стереть", "очистить", "delete", "remove", "clear", "отменить", "отмена"],
            "download": ["скачать", "загрузить", "download", "upload", "файл", "документ"],
            "legal": ["соглашение", "условия", "правила", "terms", "agreement", "policy", "политика"],
            "contact": ["контакты", "обратная связь", "contact", "support", "поддержка"],
            "search": ["поиск", "найти", "search", "find", "искать"],
            "navigation": ["главная", "home", "назад", "back", "вперед", "forward", "меню", "menu"],
            "settings": ["настройки", "settings", "профиль", "profile", "аккаунт", "account"],
        }
    
    def _load_domain_categories(self) -> Dict[str, List[str]]:
        """Категории доменов для анализа."""
        return {
            "social": ["facebook.com", "twitter.com", "instagram.com", "vk.com", "tiktok.com", "linkedin.com"],
            "shopping": ["amazon.com", "aliexpress.com", "ebay.com", "wildberries.ru", "ozon.ru", "yandex.market"],
            "banking": ["sberbank.ru", "tinkoff.ru", "alfabank.ru", "vtb.ru", "raiffeisen.ru", "gazprombank.ru"],
            "email": ["gmail.com", "mail.ru", "yandex.ru", "outlook.com", "yahoo.com", "rambler.ru"],
            "government": ["gov.ru", "gosuslugi.ru", "nalog.ru", "pfr.gov.ru", "mkgu.mos.ru"],
            "search": ["google.com", "yandex.ru", "bing.com", "duckduckgo.com"],
        }
    
    async def analyze(self, action_type: ActionType, target: str, 
                     raw_context: Dict[str, Any]) -> Dict[str, Any]:
        """Проанализировать контекст действия."""
        context = raw_context.copy()
        
        # 1. Анализ паттернов в тексте
        pattern_analysis = await self.pattern_matcher.extract_sensitive_data(target)
        context.update({
            "pattern_analysis": pattern_analysis,
            "detected_patterns": pattern_analysis.get("patterns", {}),
        })
        
        # 2. Определение типа страницы
        current_url = context.get("current_url", "")
        if current_url:
            page_analysis = self._analyze_page_type(current_url)
            context.update(page_analysis)
        
        # 3. Анализ домена
        if current_url:
            domain_analysis = self._analyze_domain(current_url)
            context.update(domain_analysis)
        
        # 4. Анализ URL для навигации
        if action_type in [ActionType.NAVIGATE, ActionType.NAVIGATE_EXTERNAL, ActionType.NAVIGATE_SUSPICIOUS]:
            target_url = context.get("target_url", target)
            if target_url:
                url_analysis = self._analyze_navigation_url(target_url, current_url)
                context.update(url_analysis)
        
        # 5. Анализ ключевых слов
        keyword_analysis = self._analyze_keywords(target)
        context.update(keyword_analysis)
        
        # 6. Анализ последовательности действий
        if "recent_history" in context:
            sequence_analysis = self._analyze_sequence(
                context["recent_history"], action_type, target
            )
            context.update(sequence_analysis)
        
        # 7. Анализ типа действия в контексте
        action_context_analysis = self._analyze_action_context(action_type, target, context)
        context.update(action_context_analysis)
        
        # 8. Расчет уверенности
        context["confidence"] = self._calculate_confidence(context)
        
        # 9. Генерация рекомендаций
        context["recommendations"] = self._generate_recommendations(context)
        
        return context
    
    def _analyze_page_type(self, url: str) -> Dict[str, bool]:
        """Определить тип страницы по URL."""
        if not url:
            return {}
        
        url_lower = url.lower()
        
        return {
            "is_login_page": any(word in url_lower for word in ["login", "signin", "auth", "вход", "войти", "account"]),
            "is_payment_page": any(word in url_lower for word in ["checkout", "payment", "pay", "cart", "корзин", "оплат", "order"]),
            "is_registration_page": any(word in url_lower for word in ["register", "signup", "регистрация", "create.account"]),
            "is_settings_page": any(word in url_lower for word in ["settings", "настройки", "profile", "профиль", "account"]),
            "is_admin_page": any(word in url_lower for word in ["admin", "админ", "dashboard", "панель", "control"]),
            "is_social_page": any(word in url_lower for word in ["facebook", "twitter", "vk", "instagram", "tiktok", "social"]),
            "is_search_page": any(word in url_lower for word in ["search", "поиск", "google", "yandex", "bing"]),
            "is_email_page": any(word in url_lower for word in ["mail", "email", "почта", "gmail", "outlook"]),
        }
    
    def _analyze_domain(self, url: str) -> Dict[str, Any]:
        """Проанализировать домен."""
        domain = extract_domain(url)
        if not domain:
            return {}
        
        domain_lower = domain.lower()
        
        # Определяем категорию домена
        domain_category = "other"
        for category, domains in self.domain_categories.items():
            for domain_pattern in domains:
                if domain_lower.endswith(domain_pattern.lower()):
                    domain_category = category
                    break
            if domain_category != "other":
                break
        
        return {
            "domain": domain,
            "domain_category": domain_category,
            "is_suspicious_domain": is_suspicious_domain(domain),
            "is_trusted_domain": domain_category in ["banking", "government", "email"],
        }
    
    def _analyze_navigation_url(self, target_url: str, current_url: str) -> Dict[str, Any]:
        """Проанализировать URL для навигации."""
        return {
            "is_external_domain": is_external_domain(current_url, target_url),
            "is_https": target_url.startswith("https://"),
            "is_http": target_url.startswith("http://"),
            "is_suspicious_url": is_suspicious_domain(extract_domain(target_url)),
        }
    
    def _analyze_keywords(self, text: str) -> Dict[str, bool]:
        """Проанализировать ключевые слова."""
        if not text:
            return {}
        
        text_lower = text.lower()
        result = {}
        
        for category, keywords in self.keyword_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    result[f"contains_{category}"] = True
                    break
        
        return result
    
    def _analyze_sequence(self, history: List[Dict], current_action: ActionType, target: str) -> Dict[str, Any]:
        """Проанализировать последовательность действий."""
        if not history:
            return {}
        
        # Анализ последних 5 действий
        recent = history[-5:] if len(history) >= 5 else history
        
        # Извлекаем типы действий и цели
        action_types = [h.get("action_type", "") for h in recent]
        targets = [str(h.get("target", "")).lower() for h in recent]
        
        # Проверка паттернов поведения
        is_login_flow = (
            ActionType.TYPE_EMAIL.value in action_types and
            ActionType.TYPE_PASSWORD.value in action_types
        )
        
        is_payment_flow = (
            any("payment" in t for t in targets) or
            any("купить" in t for t in targets) or
            any("оплатить" in t for t in targets)
        )
        
        is_registration_flow = (
            any("регистрация" in t for t in targets) or
            any("register" in t for t in targets)
        )
        
        is_form_filling = (
            len([a for a in action_types if a.startswith("TYPE_")]) >= 2
        )
        
        return {
            "is_login_flow": is_login_flow,
            "is_payment_flow": is_payment_flow,
            "is_registration_flow": is_registration_flow,
            "is_form_filling": is_form_filling,
            "recent_action_types": action_types,
            "recent_targets": targets[:3],  # Только первые 3 для экономии места
        }
    
    def _analyze_action_context(self, action_type: ActionType, target: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Проанализировать контекст конкретного действия."""
        result = {}
        
        # Для ввода пароля в контексте логина
        if action_type == ActionType.TYPE_PASSWORD and context.get("is_login_page"):
            result["is_password_in_login_context"] = True
        
        # Для оплаты на странице оплаты
        if action_type == ActionType.PAYMENT and context.get("is_payment_page"):
            result["is_payment_in_checkout_context"] = True
        
        # Для удаления в настройках
        if action_type == ActionType.DELETE and context.get("is_settings_page"):
            result["is_delete_in_settings_context"] = True
        
        # Для социальных действий на социальных страницах
        if action_type == ActionType.SOCIAL_ACTION and context.get("is_social_page"):
            result["is_social_action_in_context"] = True
        
        return result
    
    def _calculate_confidence(self, context: Dict[str, Any]) -> float:
        """Рассчитать уверенность в анализе."""
        confidence_factors = []
        
        # Паттерны в тексте
        if context.get("detected_patterns"):
            patterns = context["detected_patterns"]
            total_patterns = sum(len(matches) for category in patterns.values() 
                               for matches in category.values())
            confidence_factors.append(min(total_patterns * 0.2, 1.0))
        
        # Контекстные признаки
        if context.get("is_login_page") and context.get("contains_login"):
            confidence_factors.append(0.8)
        
        if context.get("is_payment_page") and context.get("contains_payment"):
            confidence_factors.append(0.9)
        
        # Последовательность действий
        if context.get("is_login_flow"):
            confidence_factors.append(0.85)
        
        if context.get("is_payment_flow"):
            confidence_factors.append(0.95)
        
        # Доверенные домены
        if context.get("is_trusted_domain"):
            confidence_factors.append(0.7)
        
        return sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
    
    def _generate_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """Сгенерировать рекомендации на основе контекста."""
        recommendations = []
        
        if context.get("contains_passwords", False):
            recommendations.append("🔐 Обнаружен ввод пароля - будьте осторожны")
        
        if context.get("contains_financial", False):
            recommendations.append("💰 Обнаружены финансовые данные - проверьте безопасность")
        
        if context.get("is_external_domain", False):
            recommendations.append("🌍 Переход на внешний домен - убедитесь в его надежности")
        
        if context.get("is_suspicious_domain", False):
            recommendations.append("🚫 Подозрительный домен - рекомендуется отменить переход")
        
        if not context.get("is_https", True) and context.get("contains_payment", False):
            recommendations.append("🔓 Оплата через HTTP - небезопасно, используйте HTTPS")
        
        return recommendations
    
    async def get_context_features(self) -> List[str]:
        """Получить список доступных фич контекста."""
        return [
            "page_type_analysis",
            "domain_analysis", 
            "keyword_analysis",
            "pattern_detection",
            "sequence_analysis",
            "action_context_analysis",
            "confidence_scoring",
            "recommendations_generation"
        ]
    
    def get_keyword_patterns(self) -> Dict[str, List[str]]:
        """Получить ключевые слова для анализа."""
        return self.keyword_patterns.copy()