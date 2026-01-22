"""
Оценка рисков действий.
"""
from typing import Dict, Any, List
from security.interfaces import IRiskAssessor, ActionType, RiskAssessment

class RiskAssessor(IRiskAssessor):
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.risk_weights = self._load_risk_weights()
    
    def _load_risk_weights(self) -> Dict[str, Dict[str, float]]:
        """Загрузить веса рисков."""
        return {
            "action_type": {
                # Типы ввода
                "type": 0.5,  # Обычный ввод текста
                "type_password": 80.0,  # Ввод пароля
                "type_email": 2.0,  # Ввод email - СНИЖЕННЫЙ РИСК
                "type_phone": 1.5,  # Ввод телефона
                "type_card": 89.0,  # Ввод данных карты
                "type_personal": 2.0,  # Ввод персональных данных
                
                # Типы кликов
                "click": 1.0,  # Общий клик
                "click_button": 1.0,  # Клик по кнопке
                "click_link": 0.8,  # Клик по ссылке
                
                # Навигация - СНИЖЕННЫЙ РИСК
                "navigate": 0.2,  # Обычная навигация - НИЗКИЙ РИСК
                "navigate_external": 0.3,  # Внешняя навигация - НИЗКИЙ РИСК
                "navigate_suspicious": 1.0,  # Подозрительная навигация - СРЕДНИЙ РИСК
                
                # Действия
                "form_submit": 1.5,  # Отправка формы
                "payment": 60.0,  # Платежи
                "delete": 25.0,  # Удаление
                "social_action": 1.5,  # Социальные действия
                "legal_action": 1.5,  # Юридические действия
                "scroll": 0.1,  # Прокрутка
                "analyze": 0.0,  # Анализ
            },
            "context": {
                # Типы страниц
                "is_payment_page": 1.3,
                "is_login_page": 1.1,  # СНИЖЕННЫЙ МОДИФИКАТОР
                "is_registration_page": 1.2,
                "is_settings_page": 1.1,
                "is_admin_page": 1.5,
                "is_social_page": 1.1,
                "is_search_page": 0.9,
                "is_email_page": 1.1,  # СНИЖЕННЫЙ МОДИФИКАТОР
                
                # Паттерны данных
                "contains_financial": 1.5,
                "contains_passwords": 1.8,
                "contains_personal_data": 1.3,
                "contains_contact_info": 1.1,  # СНИЖЕННЫЙ МОДИФИКАТОР
                
                # Навигация - СНИЖЕННЫЕ МОДИФИКАТОРЫ
                "is_external_domain": 1.0,  # НЕ МЕНЯЕТ РИСК
                "is_suspicious_domain": 1.2,  # НЕМНОГО ПОВЫШАЕТ
                "is_trusted_domain": 0.9,
                "is_https": 0.9,
                "is_http": 1.1,  # СЛАБОЕ ПОВЫШЕНИЕ
                
                # Потоки действий
                "is_login_flow": 1.3,  # СНИЖЕННЫЙ МОДИФИКАТОР
                "is_payment_flow": 1.8,
                "is_registration_flow": 1.3,
                "is_form_filling": 1.2,
                
                # Контекстные совпадения
                "is_password_in_login_context": 1.4,
                "is_payment_in_checkout_context": 1.6,
                "is_delete_in_settings_context": 1.7,
                "is_social_action_in_context": 1.1,
                
                # Уверенность
                "confidence_high": 1.1,  # СЛАБОЕ ПОВЫШЕНИЕ
                "confidence_low": 0.9,   # СЛАБОЕ ПОНИЖЕНИЕ
            }
        }
    
    async def assess_risk(self, action_type: ActionType, target: str,
                         context: Dict[str, Any]) -> RiskAssessment:
        """Оценить риск действия."""
        
        # Получаем ключ действия в нижнем регистре
        action_key = action_type.value.lower()
        
        # Базовый риск от типа действия
        base_risk = self.risk_weights["action_type"].get(
            action_key, 1.0  # Значение по умолчанию
        )
        
        # Модификаторы от контекста
        context_modifier = 1.0
        triggered_rules = []
        
        # Исключение для навигации - меньше контекстных модификаторов
        is_navigation = action_key in ["navigate", "navigate_external", "navigate_suspicious"]
        
        for context_key, weight in self.risk_weights["context"].items():
            if context.get(context_key, False):
                # Для навигации применяем только основные модификаторы
                if is_navigation:
                    if context_key in ["is_suspicious_domain", "is_http", "is_https"]:
                        context_modifier *= weight
                        triggered_rules.append(f"context_{context_key}")
                else:
                    context_modifier *= weight
                    triggered_rules.append(f"context_{context_key}")
        
        # Модификатор от уверенности
        confidence = context.get("confidence", 0.5)
        if confidence > 0.7:
            confidence_modifier = self.risk_weights["context"].get("confidence_high", 1.0)
        elif confidence < 0.3:
            confidence_modifier = self.risk_weights["context"].get("confidence_low", 1.0)
        else:
            confidence_modifier = 1.0
        
        # Итоговый риск
        total_risk = base_risk * context_modifier * confidence_modifier
        
        # Нормализуем до 0-100
        normalized_score = min(total_risk * 20, 100)
        
        # Для навигации искусственно ограничиваем максимальный риск
        if is_navigation:
            normalized_score = min(normalized_score, 25)  # Максимум low риск
        
        # Определяем уровень риска
        if normalized_score >= 80:
            risk_level = "critical"
        elif normalized_score >= 60:
            risk_level = "high"
        elif normalized_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Рекомендации
        recommendations = []
        if risk_level in ["high", "critical"]:
            recommendations.append("⚠️ Требуется подтверждение пользователя")
        if context.get("contains_passwords"):
            recommendations.append("🔐 Пароли никогда не должны храниться в логах")
        if context.get("contains_financial"):
            recommendations.append("💰 Финансовые операции требуют особого внимания")
        if context.get("is_suspicious_domain"):
            recommendations.append("🚫 Подозрительный домен, рекомендуется отмена")
        if not context.get("is_https", True) and base_risk > 10:
            recommendations.append("🔓 Действие выполняется по HTTP (небезопасно)")
        
        return RiskAssessment(
            score=normalized_score,
            level=risk_level,
            triggered_rules=triggered_rules,
            recommendations=recommendations,
            confidence=confidence
        )
    
    def get_risk_weights(self) -> Dict[str, Dict[str, float]]:
        """Получить веса рисков для конфигурации."""
        return self.risk_weights.copy()