"""
Контракты/интерфейсы для системы безопасности.
"""
from typing import Protocol, Dict, Any, List, Optional, Tuple, Callable, Awaitable
from enum import Enum
from dataclasses import dataclass
from abc import ABC, abstractmethod
import asyncio

class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ActionType(Enum):
    CLICK = "click"
    CLICK_BUTTON = "click_button"
    CLICK_LINK = "click_link"
    TYPE = "type"
    TYPE_PASSWORD = "type_password"
    TYPE_EMAIL = "type_email"
    TYPE_PHONE = "type_phone"
    TYPE_CARD = "type_card"
    TYPE_PERSONAL = "type_personal"
    NAVIGATE = "navigate"
    NAVIGATE_EXTERNAL = "navigate_external"
    NAVIGATE_SUSPICIOUS = "navigate_suspicious"
    FORM_SUBMIT = "form_submit"
    PAYMENT = "payment"
    DELETE = "delete"
    SOCIAL_ACTION = "social_action"
    LEGAL_ACTION = "legal_action"
    SCROLL = "scroll"
    ANALYZE = "analyze"

@dataclass
class RiskAssessment:
    """Оценка риска действия."""
    score: float  # 0-100
    level: str  # low, medium, high, critical
    triggered_rules: List[str]
    recommendations: List[str]
    confidence: float = 0.5

@dataclass
class SecurityRule:
    """Правило безопасности."""
    name: str
    pattern: str = ""
    action_type: Optional[ActionType] = None
    risk_level: str = "medium"
    message: str = ""
    requires_confirmation: bool = True
    regex: bool = False
    condition: Optional[Callable[[Dict], bool]] = None
    weight: float = 1.0
    context_keys: List[str] = None

@dataclass
class SecurityEvent:
    """Событие безопасности."""
    timestamp: str
    action: ActionType
    target: str
    risk_assessment: RiskAssessment
    context: Dict[str, Any]
    confirmed: bool = False
    user_decision: Optional[str] = None
    confidence: float = 0.0

class IRiskAssessor(Protocol):
    """Контракт для оценки рисков."""
    
    @abstractmethod
    async def assess_risk(
        self, 
        action_type: ActionType, 
        target: str,
        context: Dict[str, Any]
    ) -> RiskAssessment:
        """Оценить риск действия."""
        pass
    
    @abstractmethod
    def get_risk_weights(self) -> Dict[str, Dict[str, float]]:
        """Получить веса рисков для конфигурации."""
        pass

class IPatternMatcher(Protocol):
    """Контракт для поиска паттернов."""
    
    @abstractmethod
    async def find_patterns(
        self, 
        text: str, 
        pattern_type: str = "all"
    ) -> Dict[str, Dict[str, List[str]]]:
        """Найти паттерны в тексте."""
        pass
    
    @abstractmethod
    async def extract_sensitive_data(self, text: str) -> Dict[str, Any]:
        """Извлечь чувствительные данные с контекстом."""
        pass
    
    @abstractmethod
    def get_available_patterns(self) -> List[str]:
        """Получить список доступных типов паттернов."""
        pass

class IRuleEngine(Protocol):
    """Контракт для движка правил."""
    
    @abstractmethod
    async def evaluate_rules(
        self, 
        action_type: ActionType, 
        target: str,
        context: Dict[str, Any]
    ) -> Tuple[List[SecurityRule], RiskAssessment]:
        """Оценить действие по всем правилам."""
        pass
    
    @abstractmethod
    def add_rule(self, rule: SecurityRule) -> None:
        """Добавить правило."""
        pass
    
    @abstractmethod
    def remove_rule(self, rule_name: str) -> None:
        """Удалить правило."""
        pass
    
    @abstractmethod
    def get_rules_count(self) -> Dict[str, int]:
        """Получить статистику по правилам."""
        pass

class IContextAnalyzer(Protocol):
    """Контракт для анализа контекста."""
    
    @abstractmethod
    async def analyze(
        self, 
        action_type: ActionType, 
        target: str,
        raw_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Проанализировать контекст действия."""
        pass
    
    @abstractmethod
    async def get_context_features(self) -> List[str]:
        """Получить список доступных фич контекста."""
        pass
    
    @abstractmethod
    def get_keyword_patterns(self) -> Dict[str, List[str]]:
        """Получить ключевые слова для анализа."""
        pass

class IAuditLogger(Protocol):
    """Контракт для аудита и логирования."""
    
    @abstractmethod
    async def log_event(self, event: SecurityEvent) -> None:
        """Записать событие в лог."""
        pass
    
    @abstractmethod
    async def log_action(
        self, 
        action_type: ActionType, 
        target: str,
        risk_assessment: RiskAssessment,
        allowed: bool,
        context: Dict[str, Any]
    ) -> None:
        """Записать действие в лог."""
        pass
    
    @abstractmethod
    async def get_report(self, limit: int = 100) -> Dict[str, Any]:
        """Получить отчет по логам."""
        pass
    
    @abstractmethod
    async def save_to_file(self, filename: str) -> None:
        """Сохранить логи в файл."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику по логам."""
        pass

class IConfirmationRequester(Protocol):
    """Контракт для получения подтверждений."""
    
    @abstractmethod
    async def request_confirmation(
        self, 
        action_type: ActionType,
        target: str,
        risk_assessment: RiskAssessment,
        context: Dict[str, Any],
        triggered_rules: List[SecurityRule]
    ) -> Tuple[bool, Optional[str]]:
        """Запросить подтверждение действия."""
        pass
    
    @abstractmethod
    async def set_auto_confirm(self, action_hash: str) -> None:
        """Установить автоподтверждение для действия."""
        pass

class ISecurityLayer(Protocol):
    """Основной контракт слоя безопасности."""
    
    @abstractmethod
    async def check_action(
        self, 
        action_type: ActionType, 
        target: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, RiskAssessment]:
        """Проверить действие на безопасность."""
        pass
    
    @abstractmethod
    async def register_confirmation_callback(
        self,
        callback: Callable[[SecurityEvent], Awaitable[None]]
    ) -> None:
        """Зарегистрировать callback для подтверждений."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику по безопасности."""
        pass
    
    @abstractmethod
    async def save_logs(self, filename: str = "security_log.json") -> None:
        """Сохранить логи безопасности."""
        pass