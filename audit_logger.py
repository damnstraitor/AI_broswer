"""
Аудит и логирование событий безопасности.
"""
import json
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from security.interfaces import IAuditLogger, SecurityEvent, ActionType, RiskAssessment

class AuditLogger(IAuditLogger):
    def __init__(self, max_events: int = 1000):
        self.events: List[SecurityEvent] = []
        self.max_events = max_events
        self.stats = {
            "total_events": 0,
            "blocked_actions": 0,
            "confirmed_actions": 0,
            "critical_events": 0,
            "high_events": 0,
            "medium_events": 0,
            "low_events": 0,
        }
    
    async def log_event(self, event: SecurityEvent) -> None:
        """Записать событие в лог."""
        self.events.append(event)
        
        # Обновляем статистику
        self.stats["total_events"] += 1
        
        if event.risk_assessment.level == "critical":
            self.stats["critical_events"] += 1
        elif event.risk_assessment.level == "high":
            self.stats["high_events"] += 1
        elif event.risk_assessment.level == "medium":
            self.stats["medium_events"] += 1
        else:
            self.stats["low_events"] += 1
        
        if not event.confirmed:
            self.stats["blocked_actions"] += 1
        else:
            self.stats["confirmed_actions"] += 1
        
        # Ограничиваем размер лога
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
    
    async def log_action(self, action_type: ActionType, target: str,
                        risk_assessment: RiskAssessment, allowed: bool,
                        context: Dict[str, Any]) -> None:
        """Записать действие в лог."""
        event = SecurityEvent(
            timestamp=datetime.now().isoformat(),
            action=action_type,
            target=target[:200],  # Ограничиваем длину
            risk_assessment=risk_assessment,
            context=context,
            confirmed=allowed,
            user_decision="auto_allowed" if allowed else "auto_blocked",
            confidence=risk_assessment.confidence
        )
        
        await self.log_event(event)
    
    async def get_report(self, limit: int = 100) -> Dict[str, Any]:
        """Получить отчет по логам."""
        recent_events = self.events[-limit:] if self.events else []
        
        # Статистика по типам действий
        action_stats = {}
        for event in recent_events:
            action_type = event.action.value
            action_stats[action_type] = action_stats.get(action_type, 0) + 1
        
        return {
            "summary": {
                "total_events": len(self.events),
                "recent_events": len(recent_events),
                "blocked_actions": self.stats["blocked_actions"],
                "confirmed_actions": self.stats["confirmed_actions"],
                "block_rate": (
                    self.stats["blocked_actions"] / self.stats["total_events"]
                    if self.stats["total_events"] > 0 else 0
                ),
            },
            "risk_distribution": {
                "critical": self.stats["critical_events"],
                "high": self.stats["high_events"],
                "medium": self.stats["medium_events"],
                "low": self.stats["low_events"],
            },
            "action_statistics": action_stats,
            "recent_events": [
                {
                    "timestamp": e.timestamp,
                    "action": e.action.value,
                    "target": e.target,
                    "risk_score": e.risk_assessment.score,
                    "risk_level": e.risk_assessment.level,
                    "confirmed": e.confirmed,
                    "user_decision": e.user_decision,
                }
                for e in recent_events
            ]
        }
    
    async def save_to_file(self, filename: str) -> None:
        """Сохранить логи в файл."""
        report = await self.get_report(1000)  # Полный отчет
        
        # Добавляем детализированные события
        report["detailed_events"] = [
            {
                "timestamp": e.timestamp,
                "action": e.action.value,
                "target": e.target,
                "risk_assessment": {
                    "score": e.risk_assessment.score,
                    "level": e.risk_assessment.level,
                    "triggered_rules": e.risk_assessment.triggered_rules,
                    "recommendations": e.risk_assessment.recommendations,
                    "confidence": e.risk_assessment.confidence,
                },
                "context": e.context,
                "confirmed": e.confirmed,
                "user_decision": e.user_decision,
                "confidence": e.confidence,
            }
            for e in self.events[-500:]  # Последние 500 событий
        ]
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику по логам."""
        return self.stats.copy()