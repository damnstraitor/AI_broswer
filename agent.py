import json
import random
import string
import asyncio
import re
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime

# Импорты для работы с OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  Install openai: pip install openai")

# Импорты наших модулей
from config import config
from security import SecurityLayer, SecurityLevel, detect_action_type, ActionType

def generate_tool_call_id(length: int = 9) -> str:
    """Генерация уникального ID для вызова инструмента"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


class AIProvider:
    """Класс для работы с AI провайдерами через OpenAI библиотеку"""
    
    def __init__(self):
        config.validate()
        
        if not OPENAI_AVAILABLE:
            raise ImportError("Библиотека OpenAI не установлена. Установите: pip install openai")
        
        # Всегда используем библиотеку OpenAI, но с разными конфигурациями
        if config.ai_provider == "MISTRAL":
            print(f"🤖 Используем Mistral через OpenAI-совместимый API")
            self.client = OpenAI(
                api_key=config.mistral_api_key,
                base_url=config.mistral_base_url
            )
            self.model = config.mistral_model
        else:  # OPENAI
            print(f"🤖 Используем OpenAI API")
            self.client = OpenAI(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url
            )
            self.model = config.openai_model
        
        print(f"📡 Подключение к {config.ai_provider}, Модель: {self.model}")
    
    def get_completion(self, messages: List[Dict], tools: List[Dict] = None) -> Dict:
        """Получить завершение от AI модели через OpenAI библиотеку"""
        request_data = {
            "model": self.model,
            "messages": messages,
            "temperature": config.agent_temperature,
            "max_tokens": config.agent_max_tokens
        }
        
        if tools:
            request_data["tools"] = tools
            request_data["tool_choice"] = "auto"
        
        try:
            print(f"📡 Отправка запроса к {config.ai_provider}...")
            
            response = self.client.chat.completions.create(**request_data)
            
            message = response.choices[0].message
            
            result = {
                "content": message.content,
                "tool_calls": []
            }
            
            if hasattr(message, 'tool_calls') and message.tool_calls:
                print(f"🛠️  Получены вызовы инструментов: {len(message.tool_calls)}")
                for tool_call in message.tool_calls:
                    result["tool_calls"].append({
                        "id": generate_tool_call_id(),
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    })
            
            return result
            
        except Exception as e:
            print(f"❌ Ошибка AI ({config.ai_provider}): {e}")
            # Возвращаем безопасный ответ для продолжения
            return {"content": "Continue with the task.", "tool_calls": []}


class AutonomousAgent:
    """Автономный агент для управления браузером"""
    
    def __init__(self, ai_provider: AIProvider, browser):
        self.ai = ai_provider
        self.browser = browser
        self.history = []
        self.current_task = ""
        
        # Инициализация системы безопасности
        self.security = SecurityLayer(config.security_level)
        
        # Системный промпт для агента
        self.system_prompt = """Ты автономный AI агент для управления веб-браузером.

ТВОЯ ЗАДАЧА: Выполнять задачи пользователя, используя доступные инструменты.

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
1. analyze_page - получить информацию о текущей странице
2. click_element - кликнуть на элемент по тексту
3. type_text - ввести текст
4. navigate - перейти по URL
5. scroll_down - прокрутить страницу

ИНСТРУКЦИЯ:
1. Всегда начинай с analyze_page чтобы понять текущую страницу
2. Используй точные описания элементов (1-3 слова)
3. После каждого действия проверяй результат
4. Когда задача выполнена - сообщи об этом

ФОРМАТ:
- Для вызова инструментов: используй правильный JSON формат ТОЛЬКО с нужными аргументами
- Для ответов: будь краток и точен
- Для завершения: скажи "ЗАДАЧА ВЫПОЛНЕНА"

ВАЖНО:
- Аргументы инструментов должны быть ТОЛЬКО в формате JSON
- Не добавляй лишний текст к вызовам инструментов
- Каждый вызов инструмента должен быть отдельным действием

НАЧНИ С analyze_page. проверяй содержание каждого всплывающего окна"""

    def get_tools_schema(self) -> List[Dict]:
        """Получить схему инструментов для AI"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "analyze_page",
                    "description": "Получить информацию о текущей странице: заголовок, URL, интерактивные элементы",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "click_element",
                    "description": "Кликнуть на элемент (кнопку, ссылку, иконку) по тексту на элементе",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "Текст на элементе для клика (1-3 слова, точное совпадение)"
                            }
                        },
                        "required": ["description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "type_text",
                    "description": "Ввести текст в активное поле ввода",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string", 
                                "description": "Текст для ввода"
                            }
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "navigate",
                    "description": "Перейти на указанный URL",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "Полный URL для перехода (начинается с http:// или https://)"
                            }
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "scroll_down",
                    "description": "Прокрутить страницу вниз",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pixels": {
                                "type": "integer",
                                "description": "Количество пикселей для прокрутки",
                                "default": 500
                            }
                        }
                    }
                }
            }
        ]
    
    async def _execute_with_security(self, tool_name: str, tool_args: Dict) -> str:
            """Выполнить действие с проверкой безопасности"""
            
            # Собираем предварительный контекст для определения типа действия
            context_pre = {
                "current_url": await self.browser.get_current_url(),
                "task": self.current_task,
                "step": len(self.history) + 1,
                "recent_history": self.history[-3:] if len(self.history) >= 3 else self.history
            }
            
            # Определяем тип действия используя новую функцию из security
            action_type = detect_action_type(tool_name, tool_args, context_pre)
            
            # Получаем цель действия
            target = ""
            if tool_name == "click_element":
                target = tool_args.get("description", "")
            elif tool_name == "type_text":
                target = tool_args.get("text", "")
            elif tool_name == "navigate":
                target = tool_args.get("url", "")
            
            # Получаем дополнительную информацию от браузера
            page_content = await self.browser.get_full_page_text()
            
            # Формируем полный контекст для безопасности
            security_context = {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "current_url": await self.browser.get_current_url(),
                "target_url": target if tool_name == "navigate" else "",
                "step_number": len(self.history) + 1,
                "task": self.current_task,
                "page_content": page_content[:1000],
                "current_action": target,
                "recent_history": self.history[-5:] if len(self.history) >= 5 else self.history,
                "timestamp": datetime.now().isoformat()
            }
            
            # Проверяем действие на безопасность с новым SecurityLayer
            is_allowed, risk_assessment = await self.security.check_action(
                action_type, target, security_context
            )
            
            # Логируем проверку безопасности
            if risk_assessment.score > 30:
                print(f"   🔒 Безопасность: {risk_assessment.level.upper()} риск ({risk_assessment.score:.1f}/100)")
                if risk_assessment.triggered_rules:
                    print(f"   📜 Правила: {', '.join(risk_assessment.triggered_rules[:3])}")
            
            if not is_allowed:
                block_reason = f"❌ Действие заблокировано: {risk_assessment.level.upper()} риск"
                if risk_assessment.triggered_rules:
                    block_reason += f" (правила: {', '.join(risk_assessment.triggered_rules[:2])})"
                if risk_assessment.recommendations:
                    block_reason += f"\n   💡 {risk_assessment.recommendations[0]}"
                return block_reason
            
            # Выполняем действие
            try:
                if tool_name == "analyze_page":
                    page_info = await self.browser.get_page_summary()
                    
                    # Форматируем информацию для AI
                    elements_text = "\n".join([
                        f"- {elem['text']} ({'input' if elem['is_input'] else 'button' if elem['is_button'] else 'link'})"
                        for elem in page_info['interactive_elements'][:15]
                    ]) if page_info['interactive_elements'] else "Нет интерактивных элементов"
                    
                    result = f"""📄 СТРАНИЦА: {page_info['title']}
    🔗 URL: {page_info['url']}
    🎯 Тип страницы: {page_info['page_type']}
    🎯 Интерактивные элементы ({page_info['element_count']}):
    {elements_text}"""
                    
                    if page_info['element_count'] > 15:
                        result += f"\n... и ещё {page_info['element_count'] - 15} элементов"
                    
                    return result
                
                elif tool_name == "click_element":
                    desc = tool_args.get("description", "")
                    success, element_info = await self.browser.click_element(desc)
                    
                    if success:
                        return f"✅ Успешный клик: '{desc}' {element_info}"
                    else:
                        return f"❌ Не удалось кликнуть: '{desc}'"
                
                elif tool_name == "type_text":
                    text = tool_args.get("text", "")
                    success, is_password_field = await self.browser.type_text(text)
                    
                    if success:
                        if is_password_field:
                            return f"✅ Введен текст (в поле пароля): '{text[:20]}...'"
                        return f"✅ Введен текст: '{text[:50]}'"
                    else:
                        return f"❌ Не удалось ввести текст: '{text[:50]}'"
                
                elif tool_name == "navigate":
                    url = tool_args.get("url", "")
                    success, new_url = await self.browser.goto(url)
                    
                    if success:
                        return f"✅ Переход на: {new_url}"
                    else:
                        return f"❌ Не удалось перейти на: {url}"
                
                elif tool_name == "scroll_down":
                    pixels = tool_args.get("pixels", 500)
                    success = await self.browser.scroll_down(pixels)
                    
                    if success:
                        return f"✅ Прокручено на {pixels}px"
                    else:
                        return f"❌ Не удалось прокрутить"
                
                else:
                    return f"❌ Неизвестный инструмент: {tool_name}"
                    
            except Exception as e:
                error_msg = f"❌ Ошибка выполнения {tool_name}: {str(e)}"
                print(f"   {error_msg}")
                return error_msg
        
    async def _get_current_page_analysis(self) -> str:
        """Получить анализ текущей страницы"""
        try:
            page_info = await self.browser.get_page_summary()
            
            elements_text = "\n".join([
                f"- {elem['text']} ({'input' if elem['is_input'] else 'button' if elem['is_button'] else 'link'})"
                for elem in page_info['interactive_elements'][:10]
            ]) if page_info['interactive_elements'] else "Нет интерактивных элементов"
            
            return f"""📊 ТЕКУЩАЯ СТРАНИЦА:
Заголовок: {page_info['title']}
URL: {page_info['url']}
Тип: {page_info['page_type']}
Интерактивные элементы: {page_info['element_count']}
{elements_text}"""
            
        except Exception as e:
            return f"❌ Ошибка анализа страницы: {e}"
    
    async def solve(self, task: str) -> str:
        """Основной метод для решения задачи"""
        print(f"\n🎯 Получена задача: {task}")
        self.current_task = task
        
        # Инициализация истории сообщений
        messages = [
            {"role": "system", "content": self.system_prompt},
        ]
        
        tools_schema = self.get_tools_schema()
        
        # Счётчик шагов для мониторинга
        step = 0
        max_steps = config.agent_max_steps
        
        while True:
            step += 1
            if step > max_steps:
                print(f"⚠️  Достигнут максимальный лимит шагов ({max_steps})")
                await self.security.save_logs(config.security_log_file)
                return "⚠️ Задача не завершена (достигнут максимальный лимит шагов). Возможно, задача слишком сложна."
            
            print(f"\n📝 Шаг {step}:")
            
            try:
                # Автоматически добавляем анализ текущей страницы перед каждым шагом
                current_analysis = await self._get_current_page_analysis()
                
                # Добавляем анализ страницы в историю
                if step == 1:
                    # В первый шаг добавляем задачу и анализ
                    messages.append({"role": "user", "content": f"Задача: {task}\n\n{current_analysis}\n\nНачни выполнение задачи."})
                else:
                    # В последующие шаги добавляем только анализ
                    messages.append({"role": "user", "content": f"Текущее состояние:\n{current_analysis}\n\nПродолжай выполнять задачу."})
                
                # Получаем ответ от AI через OpenAI библиотеку
                response = self.ai.get_completion(messages, tools_schema)
                
                if response.get("tool_calls"):
                    # AI хочет вызвать инструменты
                    for tool_call in response["tool_calls"]:
                        tool_name = tool_call["function"]["name"]
                        tool_id = tool_call.get("id", generate_tool_call_id())
                        
                        # Очистка аргументов от лишнего текста
                        raw_args = tool_call["function"]["arguments"]
                        if raw_args:
                            # Удаляем лишний текст до и после JSON
                            json_match = re.search(r'\{.*\}', raw_args, re.DOTALL)
                            if json_match:
                                cleaned_args = json_match.group()
                            else:
                                cleaned_args = raw_args
                            
                            # Удаляем markdown коды
                            cleaned_args = cleaned_args.replace('```json', '').replace('```', '').strip()
                            
                            try:
                                tool_args = json.loads(cleaned_args)
                            except json.JSONDecodeError:
                                print(f"❌ Ошибка парсинга аргументов: {raw_args[:100]}")
                                # Пробуем извлечь аргументы другими способами
                                if tool_name == "navigate" and "http" in raw_args:
                                    # Пытаемся извлечь URL
                                    url_match = re.search(r'https?://[^\s)\]]+', raw_args)
                                    if url_match:
                                        tool_args = {"url": url_match.group()}
                                    else:
                                        tool_args = {}
                                elif tool_name == "type_text" and "text" in raw_args.lower():
                                    # Пытаемся извлечь текст
                                    text_match = re.search(r'"text"\s*:\s*"([^"]+)"', raw_args)
                                    if text_match:
                                        tool_args = {"text": text_match.group(1)}
                                    else:
                                        tool_args = {}
                                elif tool_name == "click_element" and "description" in raw_args.lower():
                                    # Пытаемся извлечь описание
                                    desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', raw_args)
                                    if desc_match:
                                        tool_args = {"description": desc_match.group(1)}
                                    else:
                                        tool_args = {}
                                else:
                                    tool_args = {}
                        else:
                            tool_args = {}
                        
                        # Логируем вызов инструмента
                        args_str = json.dumps(tool_args, ensure_ascii=False)[:100]
                        print(f"🔧 {tool_name}({args_str})")
                        
                        # Добавляем вызов инструмента в историю
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(tool_args) if tool_args else "{}"
                                }
                            }]
                        })
                        
                        # Выполняем инструмент с проверкой безопасности
                        result = await self._execute_with_security(tool_name, tool_args)
                        print(f"   📝 {result}")
                        
                        # Добавляем результат в историю
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": result
                        })
                        
                        # Сохраняем в историю агента
                        self.history.append({
                            "step": step,
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result[:200],
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif response.get("content"):
                    # AI отправил текстовый ответ
                    content = response["content"]
                    print(f"💭 {content}")
                    
                    # Добавляем ответ в историю
                    messages.append({"role": "assistant", "content": content})
                    
                    # Проверяем, завершена ли задача
                    completion_phrases = [
                        "ЗАДАЧА ВЫПОЛНЕНА",
                        "TASK COMPLETED",
                        "ЗАДАНИЕ ВЫПОЛНЕНО",
                        "УСПЕШНО ЗАВЕРШЕНО",
                        "МОЖНО ЗАВЕРШАТЬ",
                        "ВЫПОЛНИЛ",
                        "ГОТОВО"
                    ]
                    
                    content_upper = content.upper()
                    if any(phrase in content_upper for phrase in completion_phrases):
                        print("✅ Задача завершена!")
                        
                        # Сохраняем логи безопасности
                        await self.security.save_logs(config.security_log_file)
                        
                        # Возвращаем финальный результат
                        final_result = f"✅ ЗАДАЧА ВЫПОЛНЕНА (шагов: {step})\n\n{content}"
                        
                        # Добавляем отчет о безопасности
                        security_report = self.get_security_report()
                        if security_report["total_events"] > 0:
                            final_result += f"\n\n📊 ОТЧЕТ БЕЗОПАСНОСТИ:\n"
                            final_result += f"• Проверено действий: {security_report['total_events']}\n"
                            final_result += f"• Заблокировано: {security_report['blocked_actions']}\n"
                            final_result += f"• Уровень риска: {security_report['highest_risk']}"
                        
                        return final_result
            
            except KeyboardInterrupt:
                print("\n⚠️  Задача прервана пользователем")
                return "⚠️ Задача прервана пользователем"
            
            except Exception as e:
                print(f"❌ Ошибка на шаге {step}: {e}")
                messages.append({
                    "role": "user",
                    "content": f"Произошла ошибка: {e}. Попробуй продолжить выполнение задачи."
                })
        
        # На всякий случай (не должно выполняться)
        return "⚠️ Задача не завершена по неизвестной причине."
    
    def get_security_report(self) -> Dict:
        """Получить отчет о безопасности"""
        stats = self.security.get_stats()
        audit_stats = stats.get("audit_stats", {})
        
        total_events = audit_stats.get("total_events", 0)
        blocked_actions = audit_stats.get("blocked_actions", 0)
        
        # Определяем наивысший уровень риска из статистики
        highest_risk = "low"
        risk_distribution = stats.get("risk_distribution", {})
        
        if risk_distribution.get("critical", 0) > 0:
            highest_risk = "critical"
        elif risk_distribution.get("high", 0) > 0:
            highest_risk = "high"
        elif risk_distribution.get("medium", 0) > 0:
            highest_risk = "medium"
        
        return {
            "total_events": total_events,
            "blocked_actions": blocked_actions,
            "highest_risk": highest_risk,
            "security_level": stats.get("security_level", "unknown")
        }