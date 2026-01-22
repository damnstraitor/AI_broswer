import os
from dataclasses import dataclass
from dotenv import load_dotenv
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Callable, Awaitable

load_dotenv()

class SecurityLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

@dataclass
class Config:
    """Конфигурация приложения"""
    
    # AI Provider
    ai_provider: str = os.getenv("AI_PROVIDER", "OPENAI").upper()
    
    # Mistral (через OpenAI-совместимый API)
    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
    mistral_base_url: str = os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
    
    # OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    
    # Browser
    headless: bool = os.getenv("HEADLESS", "false").lower() == "true"
    slow_mo: int = int(os.getenv("SLOW_MO", "1000"))
    user_data_dir: str = os.path.abspath(os.getenv("USER_DATA_DIR", "./browser_data"))
    
    # Security
    security_level: SecurityLevel = SecurityLevel(os.getenv("SECURITY_LEVEL", "medium").lower())
    security_log_file: str = os.getenv("SECURITY_LOG_FILE", "security_log.json")
    
    # Agent
    agent_max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "200"))
    agent_temperature: float = float(os.getenv("AGENT_TEMPERATURE", "0.1"))
    agent_max_tokens: int = int(os.getenv("AGENT_MAX_TOKENS", "1000"))
    
    # Browser Automation
    browser_timeout: int = int(os.getenv("BROWSER_TIMEOUT", "30000"))
    default_viewport_width: int = int(os.getenv("DEFAULT_VIEWPORT_WIDTH", "1280"))
    default_viewport_height: int = int(os.getenv("DEFAULT_VIEWPORT_HEIGHT", "800"))
    
    # 🆕 Новые настройки для управления попапами
    auto_close_popups: bool = os.getenv("AUTO_CLOSE_POPUPS", "true").lower() == "true"
    skip_login_popups: bool = os.getenv("SKIP_LOGIN_POPUPS", "true").lower() == "true"
    popup_close_timeout: int = int(os.getenv("POPUP_CLOSE_TIMEOUT", "2000"))
    max_popups_per_page: int = int(os.getenv("MAX_POPUPS_PER_PAGE", "5"))
    
    # 🆕 Настройки для работы с SPA
    wait_for_spa_load: bool = os.getenv("WAIT_FOR_SPA_LOAD", "true").lower() == "true"
    spa_load_timeout: int = int(os.getenv("SPA_LOAD_TIMEOUT", "5000"))
    detect_spa_frameworks: bool = os.getenv("DETECT_SPA_FRAMEWORKS", "true").lower() == "true"
    
    # 🆕 Настройки для улучшенного поиска элементов
    enhanced_element_detection: bool = os.getenv("ENHANCED_ELEMENT_DETECTION", "true").lower() == "true"
    element_detection_timeout: int = int(os.getenv("ELEMENT_DETECTION_TIMEOUT", "5000"))
    
    def validate(self) -> None:
        """Проверка конфигурации"""
        # AI Provider проверка
        if self.ai_provider == "MISTRAL":
            if not self.mistral_api_key:
                raise ValueError("MISTRAL_API_KEY не установлен")
            print(f"   🔧 Используется Mistral через OpenAI-совместимый API")
            print(f"   🔗 Base URL: {self.mistral_base_url}")
            print(f"   🧠 Model: {self.mistral_model}")
        elif self.ai_provider == "OPENAI":
            if not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY не установлен")
            print(f"   🔧 Используется OpenAI")
            print(f"   🔗 Base URL: {self.openai_base_url}")
            print(f"   🧠 Model: {self.openai_model}")
        else:
            raise ValueError(f"Неподдерживаемый AI провайдер: {self.ai_provider}")
        
        if self.ai_provider not in ["MISTRAL", "OPENAI"]:
            raise ValueError(f"Неподдерживаемый AI провайдер: {self.ai_provider}")
        
        # Security проверка
        if not isinstance(self.security_level, SecurityLevel):
            valid_levels = [level.value for level in SecurityLevel]
            raise ValueError(
                f"Некорректный уровень безопасности: {self.security_level}. "
                f"Допустимые значения: {valid_levels}"
            )
        
        # Числовые значения проверка
        if self.slow_mo < 0 or self.slow_mo > 5000:
            raise ValueError("SLOW_MO должен быть между 0 и 5000")
        
        if self.agent_max_steps < 1 or self.agent_max_steps > 1000:
            raise ValueError("AGENT_MAX_STEPS должен быть между 1 и 1000")
        
        if self.agent_temperature < 0 or self.agent_temperature > 2:
            raise ValueError("AGENT_TEMPERATURE должен быть между 0 и 2")
        
        if self.popup_close_timeout < 100 or self.popup_close_timeout > 10000:
            raise ValueError("POPUP_CLOSE_TIMEOUT должен быть между 100 и 10000")
        
        if self.spa_load_timeout < 1000 or self.spa_load_timeout > 30000:
            raise ValueError("SPA_LOAD_TIMEOUT должен быть между 1000 и 30000")
        
        # Создаем папку для данных браузера, если её нет
        if self.user_data_dir:
            os.makedirs(self.user_data_dir, exist_ok=True)
        
        # Создаем папку для логов безопасности
        log_dir = os.path.dirname(self.security_log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        print(f"✅ Конфигурация загружена:")
        print(f"   🤖 AI: {self.ai_provider}")
        print(f"   🔒 Безопасность: {self.security_level.value}")
        print(f"   🌐 Браузер: {'Скрытый' if self.headless else 'Видимый'}")
        print(f"   🎯 Агент: макс. {self.agent_max_steps} шагов")
        print(f"   🪟 Автозакрытие попапов: {'Вкл' if self.auto_close_popups else 'Выкл'}")
        print(f"   ⚡ Обнаружение SPA: {'Вкл' if self.wait_for_spa_load else 'Выкл'}")


config = Config()