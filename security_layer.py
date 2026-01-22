"""
Основной фасад для системы безопасности.
"""
from typing import Dict, Any, List, Optional, Tuple, Callable, Awaitable
from security.interfaces import (
    ISecurityLayer, SecurityLevel, ActionType, SecurityEvent, RiskAssessment
)
from security.utils import detect_action_type, generate_action_hash
from security.pattern_matcher import PatternMatcher
from security.context_analyzer import ContextAnalyzer
from security.risk_assessor import RiskAssessor
from security.rule_engine import RuleEngine
from security.audit_logger import AuditLogger
from security.confirmation_requester import ConfirmationRequester

class SecurityLayer(ISecurityLayer):
    def __init__(self, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        self.security_level = security_level
        
        # Инициализация компонентов
        self.pattern_matcher = PatternMatcher()
        self.context_analyzer = ContextAnalyzer(self.pattern_matcher)
        self.risk_assessor = RiskAssessor()
        self.rule_engine = RuleEngine()
        self.audit_logger = AuditLogger()
        self.confirmation_requester = ConfirmationRequester()
        
        # История действий и подтверждений
        self.action_history: List[Dict[str, Any]] = []
        self.confirmed_actions = set()
        self.confirmation_callbacks: List[Callable[[SecurityEvent], Awaitable[None]]] = []
        
        print(f"🔒 Security Layer инициализирован с уровнем: {security_level.value}")
    
    def _add_to_history(self, entry: Dict[str, Any]) -> None:
        """Добавить запись в историю."""
        # Добавляем timestamp
        from datetime import datetime
        entry["timestamp"] = datetime.now().isoformat()
        self.action_history.append(entry)
        
        # Ограничиваем размер истории
        if len(self.action_history) > 100:
            self.action_history = self.action_history[-100:]
    
    async def check_action(self, action_type: ActionType, target: str,
                          context: Optional[Dict[str, Any]] = None) -> Tuple[bool, RiskAssessment]:
        """Проверить действие на безопасность."""
        context = context or {}
        
        # 1. Добавляем в историю
        self._add_to_history({
            "action_type": action_type.value,
            "target": target[:200],
            "url": context.get("current_url", ""),
        })
        
        # 2. Анализ контекста
        context = await self.context_analyzer.analyze(action_type, target, context)
        
        # 3. Проверяем, было ли это действие уже подтверждено
        action_hash = generate_action_hash(action_type, target, context)
        if action_hash in self.confirmed_actions:
            print(f"   ✅ Действие уже подтверждено ранее")
            return True, RiskAssessment(
                score=0,
                level="low",
                triggered_rules=["previously_confirmed"],
                recommendations=[],
                confidence=1.0
            )
        
        # 4. Оценка по правилам
        triggered_rules, rule_risk = await self.rule_engine.evaluate_rules(
            action_type, target, context
        )
        
        # 5. Оценка риска
        risk_assessment = await self.risk_assessor.assess_risk(
            action_type, target, context
        )
        
        # 6. Отладочная информация
        print(f"   🔍 Оценка риска для {action_type.value}:")
        print(f"      - Правила: {rule_risk.score:.1f} ({rule_risk.level})")
        print(f"      - Риск-анализатор: {risk_assessment.score:.1f} ({risk_assessment.level})")
        print(f"      - Уверенность: {risk_assessment.confidence:.2f}")
        
        # Объединяем оценку рисков
        combined_score = max(rule_risk.score, risk_assessment.score)
        combined_level = rule_risk.level if rule_risk.score > risk_assessment.score else risk_assessment.level
        combined_rules = list(set(rule_risk.triggered_rules + risk_assessment.triggered_rules))
        
        final_risk_assessment = RiskAssessment(
            score=combined_score,
            level=combined_level,
            triggered_rules=combined_rules,
            recommendations=risk_assessment.recommendations,
            confidence=risk_assessment.confidence
        )
        
        # 7. НОВАЯ ЛОГИКА: Проверяем порог риска 20
        if final_risk_assessment.score > 20:
            print(f"   ⚠️  Риск превысил порог 20 ({final_risk_assessment.score:.1f}) - требуется подтверждение")
            
            # Запрашиваем подтверждение у пользователя
            allowed, reason = await self.confirmation_requester.request_confirmation(
                action_type, target, final_risk_assessment, context, triggered_rules
            )
            
            if allowed and reason == "approved_all":
                self.confirmed_actions.add(action_hash)
            
            # Логируем результат
            await self.audit_logger.log_action(
                action_type, target, final_risk_assessment, allowed, context
            )
            
            # Вызываем колбэки
            event = SecurityEvent(
                timestamp=context.get("timestamp", ""),
                action=action_type,
                target=target,
                risk_assessment=final_risk_assessment,
                context=context,
                confirmed=allowed,
                user_decision=reason,
                confidence=final_risk_assessment.confidence
            )
            await self._notify_callbacks(event)
            
            if not allowed:
                print(f"   ❌ Действие отклонено пользователем: {reason}")
            else:
                print(f"   ✅ Действие подтверждено пользователем: {reason}")
            
            return allowed, final_risk_assessment
        
        # 8. Если риск <= 20, проверяем по уровню безопасности
        if self.security_level == SecurityLevel.LOW:
            # НИЗКИЙ уровень: только логируем
            await self.audit_logger.log_action(
                action_type, target, final_risk_assessment, True, context
            )
            print(f"   ✅ Действие разрешено (низкий уровень безопасности)")
            return True, final_risk_assessment
        
        elif self.security_level == SecurityLevel.MEDIUM:
            # СРЕДНИЙ уровень: дополнительные проверки
            # Для подозрительной навигации запрашиваем подтверждение
            if action_type == ActionType.NAVIGATE_SUSPICIOUS and final_risk_assessment.level in ["medium", "high", "critical"]:
                print(f"   🔒 Подозрительная навигация - требуется подтверждение")
                allowed, reason = await self.confirmation_requester.request_confirmation(
                    action_type, target, final_risk_assessment, context, triggered_rules
                )
                
                if allowed and reason == "approved_all":
                    self.confirmed_actions.add(action_hash)
                
                await self.audit_logger.log_action(
                    action_type, target, final_risk_assessment, allowed, context
                )
                
                event = SecurityEvent(
                    timestamp=context.get("timestamp", ""),
                    action=action_type,
                    target=target,
                    risk_assessment=final_risk_assessment,
                    context=context,
                    confirmed=allowed,
                    user_decision=reason,
                    confidence=final_risk_assessment.confidence
                )
                await self._notify_callbacks(event)
                
                return allowed, final_risk_assessment
            
            # Для остальных действий разрешаем
            await self.audit_logger.log_action(
                action_type, target, final_risk_assessment, True, context
            )
            print(f"   ✅ Действие разрешено (средний уровень безопасности)")
            return True, final_risk_assessment
        
        elif self.security_level == SecurityLevel.HIGH:
            # ВЫСОКИЙ уровень: строгие проверки
            # Автоматически блокируем опасные действия
            if final_risk_assessment.level in ["high", "critical"]:
                print(f"   🚫 Опасное действие заблокировано автоматически (уровень риска: {final_risk_assessment.level})")
                await self.audit_logger.log_action(
                    action_type, target, final_risk_assessment, False, context
                )
                return False, final_risk_assessment
            
            # Для среднего риска запрашиваем подтверждение
            elif final_risk_assessment.level == "medium":
                print(f"   🔒 Средний риск - требуется подтверждение")
                allowed, reason = await self.confirmation_requester.request_confirmation(
                    action_type, target, final_risk_assessment, context, triggered_rules
                )
                
                await self.audit_logger.log_action(
                    action_type, target, final_risk_assessment, allowed, context
                )
                return allowed, final_risk_assessment
            
            # Для низкого риска разрешаем
            await self.audit_logger.log_action(
                action_type, target, final_risk_assessment, True, context
            )
            print(f"   ✅ Действие разрешено (высокий уровень безопасности)")
            return True, final_risk_assessment
        
        # По умолчанию разрешаем
        print(f"   ✅ Действие разрешено (по умолчанию)")
        return True, final_risk_assessment
    
    async def register_confirmation_callback(self,
                                           callback: Callable[[SecurityEvent], Awaitable[None]]) -> None:
        """Зарегистрировать callback для подтверждений."""
        self.confirmation_callbacks.append(callback)
    
    async def _notify_callbacks(self, event: SecurityEvent) -> None:
        """Уведомить все зарегистрированные колбэки."""
        for callback in self.confirmation_callbacks:
            try:
                await callback(event)
            except Exception as e:
                print(f"Ошибка в колбэке подтверждения: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику по безопасности."""
        audit_stats = self.audit_logger.get_stats()
        rule_stats = self.rule_engine.get_rules_count()
        
        return {
            "security_level": self.security_level.value,
            "audit_stats": audit_stats,
            "rule_stats": rule_stats,
            "history_size": len(self.action_history),
            "confirmed_actions": len(self.confirmed_actions),
            "risk_distribution": {
                "critical": audit_stats.get("critical_events", 0),
                "high": audit_stats.get("high_events", 0),
                "medium": audit_stats.get("medium_events", 0),
                "low": audit_stats.get("low_events", 0),
            }
        }
    
    async def save_logs(self, filename: str = "security_log.json") -> None:
        """Сохранить логи безопасности."""
        await self.audit_logger.save_to_file(filename)