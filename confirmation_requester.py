"""
Запрос подтверждений действий у пользователя.
"""
import asyncio
from typing import Dict, Any, List, Tuple, Optional
from .interfaces import IConfirmationRequester, ActionType, SecurityRule, RiskAssessment
from .utils import mask_sensitive_data, generate_action_hash

class AsyncInputProvider:
    """Асинхронный провайдер ввода от пользователя."""
    
    @staticmethod
    async def get_input(prompt: str) -> str:
        """Асинхронно получить ввод от пользователя."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)

class ConfirmationRequester(IConfirmationRequester):
    def __init__(self, input_provider=None):
        self.input_provider = input_provider or AsyncInputProvider()
        self.auto_confirm_hashes = set()
    
    async def request_confirmation(self, action_type: ActionType, target: str,
                                  risk_assessment: RiskAssessment, context: Dict[str, Any],
                                  triggered_rules: List[SecurityRule]) -> Tuple[bool, Optional[str]]:
        """Запросить подтверждение действия."""
        
        # Проверяем, не было ли это действие уже подтверждено
        action_hash = generate_action_hash(action_type, target, context)
        if action_hash in self.auto_confirm_hashes:
            return True, "previously_confirmed"
        
        # Маскируем чувствительные данные
        masked_target = mask_sensitive_data(target)
        
        # Формируем сообщение для пользователя
        message = self._format_confirmation_message(
            action_type, masked_target, risk_assessment, triggered_rules, context
        )
        
        # Детали для отображения
        details = {
            "action_type": action_type.value,
            "target": masked_target,
            "risk_score": risk_assessment.score,
            "risk_level": risk_assessment.level,
            "triggered_rules": [r.name for r in triggered_rules],
            "context_summary": self._summarize_context(context),
        }
        
        # Запрашиваем подтверждение
        return await self._get_user_decision(message, details, risk_assessment.level)
    
    def _format_confirmation_message(self, action_type: ActionType, target: str,
                                    risk_assessment: RiskAssessment,
                                    triggered_rules: List[SecurityRule],
                                    context: Dict[str, Any]) -> str:
        """Форматировать сообщение для подтверждения."""
        lines = []
        lines.append("🔒 SECURITY ALERT - Требуется подтверждение")
        lines.append("=" * 70)
        lines.append(f"\n📊 ОЦЕНКА РИСКА: {risk_assessment.level.upper()} ({risk_assessment.score:.1f}/100)")
        
        # Правила
        if triggered_rules:
            lines.append("\n📜 Сработавшие правила безопасности:")
            for rule in triggered_rules[:5]:
                lines.append(f"  ⚠️  {rule.message} [{rule.risk_level.upper()}]")
            if len(triggered_rules) > 5:
                lines.append(f"  ... и ещё {len(triggered_rules) - 5} правил")
        
        # Детали действия
        lines.append(f"\n🎯 ДЕЙСТВИЕ: {action_type.value}")
        lines.append(f"📝 ЦЕЛЬ: {target[:200]}")
        
        # Контекст
        if context.get("current_url"):
            lines.append(f"🌐 URL: {context['current_url'][:100]}")
        
        # Рекомендации
        if risk_assessment.recommendations:
            lines.append(f"\n💡 РЕКОМЕНДАЦИИ:")
            for rec in risk_assessment.recommendations:
                lines.append(f"  • {rec}")
        
        return "\n".join(lines)
    
    def _summarize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Создать краткое описание контекста."""
        summary = {}
        
        # Тип страницы
        page_types = []
        for key in ["is_login_page", "is_payment_page", "is_registration_page",
                   "is_settings_page", "is_social_page"]:
            if context.get(key):
                page_types.append(key.replace("is_", "").replace("_page", ""))
        if page_types:
            summary["page_type"] = page_types[0]
        
        # Домен
        if context.get("domain"):
            summary["domain"] = context["domain"]
        
        # Паттерны
        if context.get("detected_patterns"):
            patterns = context["detected_patterns"]
            pattern_count = sum(len(matches) for category in patterns.values() 
                              for matches in category.values())
            summary["detected_patterns_count"] = pattern_count
        
        return summary
    
    async def _get_user_decision(self, message: str, details: Dict[str, Any],
                                risk_level: str) -> Tuple[bool, Optional[str]]:
        """Получить решение от пользователя."""
        print(message)
        
        while True:
            print("\n📋 ВАРИАНТЫ:")
            print("  y - Разрешить это действие")
            print("  n - Заблокировать это действие")
            print("  a - Разрешить все подобные действия в этой сессии")
            print("  d - Показать детали")
            print("  q - Прервать задачу")
            
            try:
                # Ждем ввод пользователя
                response_raw = await self.input_provider.get_input("\nВаш выбор (y/n/a/d/q): ")
                # Преобразуем в строку и очищаем
                response = str(response_raw).lower().strip() if response_raw else ""
                
                if response == 'd':
                    print("\n📊 ДЕТАЛИ:")
                    for key, value in details.items():
                        print(f"  {key}: {value}")
                    continue
                
                elif response == 'y':
                    print("✅ Действие разрешено пользователем")
                    return True, "approved"
                
                elif response == 'a':
                    print("✅ Действие разрешено и добавлено в разрешенные")
                    return True, "approved_all"
                
                elif response == 'n':
                    print("❌ Действие заблокировано пользователем")
                    return False, "blocked"
                
                elif response == 'q':
                    print("⏹️  Задача прервана пользователем")
                    return False, "task_aborted"
                
                else:
                    print("❓ Неверный выбор. Попробуйте снова.")
                    
            except (KeyboardInterrupt, EOFError):
                print("\n⏹️  Прервано пользователем")
                return False, "interrupted"
            except Exception as e:
                print(f"❌ Ошибка ввода: {e}")
                return False, "input_error"
    
    async def set_auto_confirm(self, action_hash: str) -> None:
        """Установить автоподтверждение для действия."""
        self.auto_confirm_hashes.add(action_hash)