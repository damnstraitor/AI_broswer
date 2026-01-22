"""
AI Browser Agent v2.0 - Автономный агент для управления браузером
Основной файл запуска с поддержкой нового Security Layer
"""

import sys
import os
import asyncio
import signal
import json
from datetime import datetime
from typing import Dict, List, Any

# Добавляем корень проекта в путь Python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импорты для работы с rich (опционально)
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️  Install rich for better UI: pip install rich")

# Импорт наших модулей
from config import config
from agent import AIProvider, AutonomousAgent
from browser import BrowserController
from security import SecurityLevel


class AIConsole:
    """Класс для вывода в консоль"""
    
    def __init__(self):
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None
    
    def print(self, content, style=None):
        if self.console:
            self.console.print(content, style=style)
        else:
            print(content)
    
    def print_panel(self, title, content, subtitle=None, style="cyan"):
        if self.console:
            panel = Panel(
                content,
                title=title,
                subtitle=subtitle,
                border_style=style
            )
            self.console.print(panel)
        else:
            print(f"\n{'='*60}")
            print(f"{title}")
            if subtitle:
                print(f"{subtitle}")
            print('='*60)
            print(content)
            print('='*60)


def handle_interrupt(signum, frame):
    """Обработчик прерывания"""
    print("\n\n⚠️  Прерывание...")
    sys.exit(0)


async def main():
    """Основная функция"""
    
    # Настройка обработчика прерывания
    signal.signal(signal.SIGINT, handle_interrupt)
    
    # Инициализация консоли
    console = AIConsole()
    
    # Заголовок
    console.print_panel(
        "🤖 AI Browser Agent v2.2",
        "Автономный агент для управления браузером",
        f"Security Level: {config.security_level.value.upper()} | Model: {config.ai_provider}"
    )
    
    # Проверка конфигурации
    try:
        config.validate()
    except ValueError as e:
        console.print(f"❌ Ошибка конфигурации: {e}", style="red")
        console.print("📝 Создайте файл .env с вашим API ключом")
        console.print("   Пример .env файла в README.md")
        return
    
    # Информация о конфигурации
    console.print(f"🤖 AI Провайдер: {config.ai_provider}")
    console.print(f"🔒 Уровень безопасности: {config.security_level.value}")
    console.print(f"🌐 Режим браузера: {'Скрытый' if config.headless else 'Видимый'}")
    console.print(f"🎯 Макс. шагов агента: {config.agent_max_steps}")
    console.print(f"🎨 Разрешение: {config.default_viewport_width}x{config.default_viewport_height}")
    console.print(f"🪟 Автозакрытие попапов: {'Вкл' if config.auto_close_popups else 'Выкл'}")
    console.print(f"⚡ Обнаружение SPA: {'Вкл' if config.wait_for_spa_load else 'Выкл'}")
    
    # Запуск браузера
    console.print("🚀 Запуск браузера...")
    browser = BrowserController()
    try:
        await browser.start()
        # Проверяем соединение с тестовым переходом
        success, url = await browser.goto("https://www.google.com")
        if success:
            page_info = await browser.get_page_summary()
            console.print(f"✅ Браузер запущен: {page_info['title']}")
            console.print(f"   📍 URL: {url[:80]}")
        else:
            console.print(f"⚠️  Браузер запущен, но тестовый переход не удался: {url}", style="yellow")
    except Exception as e:
        console.print(f"❌ Ошибка запуска браузера: {e}", style="red")
        console.print("   Убедитесь, что Playwright установлен: pip install playwright")
        console.print("   И браузеры установлены: playwright install chromium")
        return
    
    # Инициализация AI провайдера
    try:
        ai_provider = AIProvider()
    except Exception as e:
        console.print(f"❌ Ошибка инициализации AI: {e}", style="red")
        await browser.close()
        return
    
    # Инициализация агента
    agent = AutonomousAgent(ai_provider, browser)
    
    # Основной цикл
    console.print_panel(
        "🚀 Система готова к работе",
        "Агент сканирует страницу перед каждым шагом и работает с учетом безопасности",
        "Примеры: 'войди в gmail', 'найди новости про AI', 'зарегистрируйся на сайте'"
    )
    
    while True:
        print("\n" + "-" * 70)
        command = input("\nВведите задачу (или 'выход' для завершения): ").strip()
        
        if command.lower() in ['выход', 'exit', 'quit', 'q']:
            console.print("👋 Завершение работы...")
            break
        
        if not command:
            continue
        
        # Выполняем задачу
        console.print_panel("🎯 Начинаем выполнение", f"Задача: {command}")
        console.print("ℹ️  Агент будет сканировать страницу перед каждым шагом")
        console.print(f"ℹ️  Максимум шагов: {config.agent_max_steps}")
        
        try:
            result = await agent.solve(command)
            
            print("\n" + "=" * 70)
            print(result)
            print("=" * 70)
            
            # Сохраняем результат
            try:
                os.makedirs("logs", exist_ok=True)
                task_record = {
                    "timestamp": datetime.now().isoformat(),
                    "task": command,
                    "result": result[:500],
                    "url": await browser.get_current_url(),
                    "steps": len(agent.history)
                }
                
                filename = f"logs/tasks_{datetime.now().strftime('%Y%m%d')}.json"
                if os.path.exists(filename):
                    with open(filename, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    existing_data.append(task_record)
                else:
                    existing_data = [task_record]
                
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)
                
                console.print(f"📁 Результат сохранен в {filename}", style="dim")
            except Exception as e:
                console.print(f"⚠️  Ошибка сохранения: {e}", style="yellow")
        
        except KeyboardInterrupt:
            console.print("\n⚠️  Задача прервана пользователем", style="yellow")
        except Exception as e:
            console.print(f"\n❌ Ошибка выполнения задачи: {e}", style="red")
            import traceback
            traceback.print_exc()
    
    # Завершение работы
    console.print("\n👋 Закрытие браузера...")
    await browser.close()
    
    # Сохраняем финальный отчет безопасности
    try:
        await agent.security.save_logs(config.security_log_file)
        console.print(f"📁 Логи безопасности сохранены в {config.security_log_file}", style="dim")
    except Exception as e:
        console.print(f"⚠️  Ошибка сохранения логов безопасности: {e}", style="yellow")
    
    console.print_panel("✅ Работа завершена", "Все данные сохранены в папке logs/")
    console.print("📊 Статистика безопасности:")
    security_report = agent.get_security_report()
    console.print(f"   • Проверено действий: {security_report['total_events']}")
    console.print(f"   • Заблокировано: {security_report['blocked_actions']}")
    console.print(f"   • Уровень риска: {security_report['highest_risk']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Программа прервана пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)