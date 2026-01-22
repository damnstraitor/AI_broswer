"""
Движок правил безопасности.
"""
import re
from typing import Dict, Any, List, Tuple, Optional, Callable
from security.interfaces import IRuleEngine, ActionType, SecurityRule, RiskAssessment

class RuleEngine(IRuleEngine):
    def __init__(self):
        self.rules: List[SecurityRule] = []
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Загрузить правила по умолчанию."""
        # Финансовые правила
        self.rules.extend([
            SecurityRule(
                name="payment_click",
                pattern=r"(купить|оплатить|покупка|заказ|checkout|buy now|add to cart|оформить|заказать|корзин|basket)",
                action_type=ActionType.CLICK_BUTTON,
                risk_level="high",
                message="💰 Кнопка оплаты/покупки",
                regex=True,
                weight=2.0
            ),
            SecurityRule(
                name="card_data_input",
                pattern=r"(карт|card|номер.*карт|cvv|cvc|срок.*действия|expir|valid|пластик)",
                action_type=ActionType.TYPE,
                risk_level="critical",
                message="💳 Ввод данных карты",
                regex=True,
                weight=3.0
            ),
        ])
        
        # Приватность
        self.rules.extend([
            SecurityRule(
                name="password_input",
                pattern=r"(пароль|password|pwd|pass|ключ|key|секрет|secret|pin|код.*доступ)",
                action_type=ActionType.TYPE,
                risk_level="critical",
                message="🔐 Ввод пароля/ключа",
                regex=True,
                weight=3.0
            ),
            # УБРАЛИ правило для email - оно вызывало слишком высокий риск
             SecurityRule(
                 name="email_input",
                 pattern=r"(@|email|емейл|почта|e-mail|mail\.|gmail\.|yandex\.)",
                 action_type=ActionType.TYPE,
                 risk_level="medium",
                 message="📧 Ввод email",
                 regex=True,
                 weight=1.5
             ),
        ])
        
        # Навигация - УБРАЛИ правила для навигации
        self.rules.extend([
             SecurityRule(
                 name="external_navigation",
                 pattern=r"(https?://|www\.|\.com|\.ru|\.org|\.net)",
                 action_type=ActionType.NAVIGATE,
                 risk_level="low",
                 message="🌍 Навигация на внешний ресурс",
                 regex=True,
                 weight=1.0
             ),
             SecurityRule(
                 name="non_https_navigation",
                 pattern=r"^http://",
                 action_type=ActionType.NAVIGATE,
                 risk_level="medium",
                 message="🔓 Навигация по HTTP (небезопасно)",
                 regex=True,
                 weight=1.5
             ),
         ])
        
        # Контекстные правила
        self.rules.extend([
            SecurityRule(
                name="context_login_flow_password",
                action_type=ActionType.TYPE_PASSWORD,
                risk_level="high",
                message="🔐 Ввод пароля в контексте логина",
                condition=lambda ctx: ctx.get("is_login_page", False),
                weight=2.5
            ),
            SecurityRule(
                name="context_payment_flow",
                action_type=ActionType.PAYMENT,
                risk_level="critical",
                message="💸 Оплата в контексте checkout",
                condition=lambda ctx: ctx.get("is_payment_page", False),
                weight=3.0
            ),
        ])
    
    async def evaluate_rules(self, action_type: ActionType, target: str,
                            context: Dict[str, Any]) -> Tuple[List[SecurityRule], RiskAssessment]:
        """Оценить действие по всем правилам."""
        triggered_rules = []
        
        for rule in self.rules:
            #print(0)
            # Проверяем, подходит ли правило для данного типа действия
            if rule.action_type and rule.action_type != action_type:
                continue
            #print(1)
            # Пропускаем правила для навигации
            if action_type in [ActionType.NAVIGATE, ActionType.NAVIGATE_EXTERNAL]:
                continue
            #print(2)
            # Проверяем дополнительные условия
            if rule.condition and not rule.condition(context):
                continue
            #print(3)
            # Проверяем соответствие паттерну
            if rule.pattern:
                if rule.regex:
                    if re.search(rule.pattern, target, re.IGNORECASE):
                        triggered_rules.append(rule)
                else:
                    if rule.pattern.lower() in target.lower():
                        triggered_rules.append(rule)
            elif rule.condition:
                # Правило только с условием
                triggered_rules.append(rule)
        
        # Оцениваем риск на основе сработавших правил
        risk_score = 0.0
        max_possible = 0.0
        print(triggered_rules)
        for rule in triggered_rules:
            weight = rule.weight
            risk_level_multiplier = {
                "low": 0.3,
                "medium": 0.6,
                "high": 0.9,
                "critical": 1.0
            }.get(rule.risk_level, 0.5)
            
            risk_score += weight * risk_level_multiplier
            max_possible += weight
        
        # Нормализуем оценку 0-100
        
        normalized_score = (risk_score / max_possible * 100) if max_possible > 0 else 0
        #print(normalized_score, risk_score)
        # Определяем уровень
        if normalized_score >= 80:
            risk_level = "critical"
        elif normalized_score >= 60:
            risk_level = "high"
        elif normalized_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Для навигации всегда low
        if action_type in [ActionType.NAVIGATE, ActionType.NAVIGATE_EXTERNAL]:
            normalized_score = 5
            risk_level = "low"
        
        risk_assessment = RiskAssessment(
            score=normalized_score,
            level=risk_level,
            triggered_rules=[r.name for r in triggered_rules],
            recommendations=[],
            confidence=context.get("confidence", 0.5)
        )
        
        return triggered_rules, risk_assessment
    
    def add_rule(self, rule: SecurityRule) -> None:
        """Добавить правило."""
        self.rules.append(rule)
    
    def remove_rule(self, rule_name: str) -> None:
        """Удалить правило."""
        self.rules = [r for r in self.rules if r.name != rule_name]
    
    def get_rules_count(self) -> Dict[str, int]:
        """Получить статистику по правилам."""
        counts = {
            "total": len(self.rules),
            "financial": len([r for r in self.rules if "финанс" in r.name or "payment" in r.name]),
            "privacy": len([r for r in self.rules if "password" in r.name or "privacy" in r.name]),
            "navigation": 0,  # Убрали правила навигации
            "context": len([r for r in self.rules if r.condition is not None]),
        }
        return counts