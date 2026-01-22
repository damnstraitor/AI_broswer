import asyncio
import os
import re
import json
import hashlib
from typing import Dict, Tuple, List, Optional, Set, Any
from playwright.async_api import async_playwright, Page, BrowserContext, ElementHandle, Locator, Response
from config import config
from datetime import datetime, timedelta


class RecoveryStrategy:
    """Система восстановления после ошибок"""
    
    def __init__(self, browser):
        self.browser = browser
        self.error_history = []
        self.max_history_size = 20
        
        # Стратегии восстановления в порядке приоритета
        self.strategies = [
            self._try_refresh_page,
            self._try_go_back,
            self._try_alternative_selector,
            self._try_keyboard_navigation,
            self._try_change_viewport,
            self._try_wait_longer,
            self._try_manual_intervention,
        ]
    
    def record_error(self, error_type: str, context: Dict, element: str = ""):
        """Записать ошибку в историю"""
        self.error_history.append({
            "timestamp": datetime.now().isoformat(),
            "error_type": error_type,
            "element": element,
            "context": context,
            "recovery_attempted": False
        })
        
        # Ограничиваем размер истории
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
        
        print(f"   📝 Записана ошибка: {error_type} для элемента '{element}'")
    
    async def recover(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """
        Попробовать восстановиться после ошибки
        
        Returns:
            Tuple[bool, str]: (успех восстановления, описание стратегии)
        """
        print(f"   🔄 Попытка восстановления после ошибки: {error_type}")
        
        # Записываем ошибку
        self.record_error(error_type, context, element)
        
        # Проверяем, не является ли это частой ошибкой
        recent_errors = [e for e in self.error_history[-5:] 
                        if e["error_type"] == error_type and e["element"] == element]
        
        if len(recent_errors) >= 3:
            print(f"   ⚠️  Частая ошибка для элемента '{element}', пропускаем...")
            return False, "Слишком частые ошибки для этого элемента"
        
        # Пробуем стратегии по порядку
        for i, strategy in enumerate(self.strategies):
            strategy_name = strategy.__name__.replace("_try_", "").replace("_", " ")
            print(f"   🔧 Стратегия {i+1}: {strategy_name}")
            
            try:
                success, message = await strategy(error_type, context, element)
                if success:
                    # Отмечаем успешное восстановление
                    for error in self.error_history[-3:]:
                        if error["element"] == element and not error.get("recovery_attempted"):
                            error["recovery_attempted"] = True
                            error["recovery_strategy"] = strategy_name
                            error["recovery_success"] = True
                    
                    print(f"   ✅ Восстановление успешно: {message}")
                    return True, f"{strategy_name}: {message}"
                    
            except Exception as e:
                print(f"   ❌ Ошибка в стратегии {strategy_name}: {e}")
                continue
        
        print(f"   ❌ Все стратегии восстановления не сработали")
        return False, "Не удалось восстановиться"
    
    async def _try_refresh_page(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Попробовать обновить страницу"""
        if error_type in ["element_not_found", "stale_element", "timeout"]:
            print(f"   🔄 Обновляю страницу...")
            await self.browser.page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Обрабатываем возможные попапы
            await self.browser.popup_manager.handle_popups()
            
            return True, "Страница обновлена"
        return False, "Не подходящий тип ошибки"
    
    async def _try_go_back(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Вернуться на предыдущую страницу"""
        if error_type in ["navigation_error", "page_not_loaded"]:
            print(f"   ↩️  Возвращаюсь на предыдущую страницу...")
            await self.browser.page.go_back(wait_until="domcontentloaded")
            await asyncio.sleep(2)
            return True, "Вернулись на предыдущую страницу"
        return False, "Не подходящий тип ошибки"
    
    async def _try_alternative_selector(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Попробовать альтернативные селекторы"""
        if error_type == "element_not_found" and element:
            print(f"   🔍 Ищу альтернативные способы найти '{element}'")
            
            # Пробуем разные варианты текста
            variations = [
                element,
                element.lower(),
                element.upper(),
                element.title(),
                element.split()[0] if " " in element else element,
                element.replace(" ", ""),
                element.replace("-", " "),
                element.replace("_", " "),
            ]
            
            for variation in variations:
                if variation and variation != element:
                    success, info = await self.browser._try_alternative_search(variation)
                    if success:
                        return True, f"Найден как '{variation}'"
            
            return False, "Альтернативные селекторы не сработали"
        return False, "Не подходящий тип ошибки"
    
    async def _try_keyboard_navigation(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Попробовать навигацию с клавиатуры"""
        if error_type in ["element_not_interactable", "element_covered"]:
            print(f"   ⌨️  Пробую навигацию с клавиатуры...")
            
            try:
                # Tab к следующему элементу
                await self.browser.page.keyboard.press("Tab")
                await asyncio.sleep(0.5)
                
                # Enter для активации
                await self.browser.page.keyboard.press("Enter")
                await asyncio.sleep(1)
                
                return True, "Навигация с клавиатуры выполнена"
            except:
                return False, "Навигация с клавиатуры не сработала"
        
        return False, "Не подходящий тип ошибки"
    
    async def _try_change_viewport(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Изменить размер viewport"""
        if error_type in ["element_not_visible", "element_out_of_view"]:
            print(f"   📱 Изменяю размер viewport...")
            
            # Пробуем разные размеры
            viewports = [
                {"width": 1024, "height": 768},
                {"width": 1280, "height": 800},
                {"width": 1440, "height": 900},
                {"width": 1920, "height": 1080},
                {"width": 375, "height": 667},  # Mobile
            ]
            
            current_size = await self.browser.page.viewport_size()
            
            for viewport in viewports:
                if viewport != current_size:
                    await self.browser.page.set_viewport_size(viewport)
                    await asyncio.sleep(1)
                    
                    # Прокручиваем немного
                    await self.browser.page.evaluate("window.scrollBy(0, 100)")
                    await asyncio.sleep(0.5)
                    
                    # Проверяем, появился ли элемент
                    try:
                        # Быстрая проверка через JS
                        element_found = await self.browser.page.evaluate(f"""
                            () => {{
                                const elements = document.querySelectorAll('*');
                                for (const el of elements) {{
                                    const text = el.innerText || el.textContent || '';
                                    if (text.toLowerCase().includes('{element.lower()}')) {{
                                        return true;
                                    }}
                                }}
                                return false;
                            }}
                        """)
                        
                        if element_found:
                            return True, f"Viewport изменен на {viewport['width']}x{viewport['height']}"
                    except:
                        continue
            
            # Возвращаем оригинальный размер
            if current_size:
                await self.browser.page.set_viewport_size(current_size)
            
            return False, "Изменение viewport не помогло"
        
        return False, "Не подходящий тип ошибки"
    
    async def _try_wait_longer(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Подождать дольше"""
        if error_type in ["timeout", "slow_loading"]:
            print(f"   ⏳ Жду дольше (5 секунд)...")
            await asyncio.sleep(5)
            
            # Дополнительная проверка загрузки
            await self.browser.wait_for_network_idle(3000)
            
            return True, "Ожидание завершено"
        return False, "Не подходящий тип ошибки"
    
    async def _try_manual_intervention(self, error_type: str, context: Dict, element: str = "") -> Tuple[bool, str]:
        """Запросить ручное вмешательство (последняя стратегия)"""
        print(f"   🆘 Требуется ручное вмешательство для ошибки: {error_type}")
        print(f"   📝 Элемент: '{element}'")
        print(f"   🌐 URL: {context.get('current_url', 'Неизвестно')}")
        
        # Делаем скриншот для отладки
        screenshot = await self.browser.take_screenshot()
        if screenshot:
            print(f"   📸 Скриншот сделан: {screenshot}")
        
        # Возвращаем false, так как это ручное вмешательство
        return False, "Требуется ручное вмешательство"
    
    def get_recovery_report(self) -> Dict:
        """Получить отчет о восстановлениях"""
        successful = [e for e in self.error_history if e.get("recovery_success")]
        failed = [e for e in self.error_history if e.get("recovery_attempted") and not e.get("recovery_success")]
        
        # Статистика по типам ошибок
        error_types = {}
        for error in self.error_history:
            error_type = error["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # Статистика по стратегиям
        strategies = {}
        for error in self.error_history:
            strategy = error.get("recovery_strategy")
            if strategy:
                strategies[strategy] = strategies.get(strategy, 0) + 1
        
        return {
            "total_errors": len(self.error_history),
            "successful_recoveries": len(successful),
            "failed_recoveries": len(failed),
            "success_rate": len(successful) / len(self.error_history) if self.error_history else 0,
            "error_types": error_types,
            "strategies_used": strategies,
            "recent_errors": self.error_history[-5:]
        }


class PopupManager:
    """Менеджер для управления всплывающими окнами"""
    
    def __init__(self, browser_controller):
        self.browser = browser_controller
        self.closed_popups: Set[str] = set()  # Хэши закрытых попапов
        self.popup_counter = 0
        
        # Типы попапов, которые можно безопасно закрывать
        self.safe_popup_selectors = [
            # Cookie и GDPR баннеры
            '.cookie-banner', '.gdpr-banner', '.cookie-notice', '.cookie-consent',
            '.privacy-banner', '.fc-consent-root', '.cc-banner',
            '#cookie-banner', '#gdpr-banner', '#cookie-notice',
            '[class*="cookie"]', '[class*="gdpr"]', '[class*="consent"]',
            
            # Рекламные попапы
            '.ad-popup', '.ad-modal', '.ad-overlay',
            '.marketing-popup', '.newsletter-popup', '.promo-popup',
            '[class*="advertisement"]', '[class*="marketing"]',
            
            # Уведомления
            '.notification', '.alert-banner', '.info-banner',
            '.site-notification', '.global-notification',
            
            # Подписки и email сбор
            '.email-popup', '.subscribe-popup', '.newsletter-modal',
            '.signup-modal', '.lead-capture',
            
            # Общие модальные окна (с осторожностью)
            '.modal-backdrop', '.modal-overlay', '.overlay',
            
            # Социальные попапы
            '.social-share', '.share-modal',
        ]
        
        # Типы попапов, которые НЕЛЬЗЯ закрывать (критически важные)
        self.dangerous_popup_selectors = [
            # Формы входа и регистрации
            '.login-modal', '.signin-modal', '.auth-modal',
            '.register-modal', '.signup-modal',
            
            # Платежные формы
            '.payment-modal', '.checkout-modal', '.cart-modal',
            '.purchase-modal', '.billing-modal',
            
            # Важные подтверждения
            '.confirmation-modal', '.confirm-dialog',
            '.delete-confirmation', '.warning-modal',
            
            # Настройки и профиль
            '.settings-modal', '.profile-modal', '.account-modal',
            
            # Формы с важными данными
            '[role="dialog"][aria-label*="login" i]',
            '[role="dialog"][aria-label*="sign in" i]',
            '[role="dialog"][aria-label*="войти" i]',
            '[role="dialog"][aria-label*="оплат" i]',
            '[role="dialog"][aria-label*="checkout" i]',
        ]
        
        # Кнопки закрытия (приоритет по порядку)
        self.close_button_selectors = [
            # Иконки закрытия
            'button:has-text("×")', 'button:has-text("X")',
            'button[aria-label*="close" i]',
            'button[aria-label*="закрыть" i]',
            'button[title*="close" i]',
            'button[title*="закрыть" i]',
            
            # Кнопки принятия соглашений
            'button:has-text("Принять")', 'button:has-text("Accept")',
            'button:has-text("Согласен")', 'button:has-text("Agree")',
            'button:has-text("OK")', 'button:has-text("ОК")',
            'button:has-text("Понятно")', 'button:has-text("Got it")',
            'button:has-text("Продолжить")', 'button:has-text("Continue")',
            
            # Кнопки закрытия по классам
            '.close', '.close-button', '.modal-close',
            '.popup-close', '.btn-close', '.close-btn',
            '.close-modal', '.close-popup',
            
            # Кнопки отмены (только для безопасных попапов)
            'button:has-text("Отмена")', 'button:has-text("Cancel")',
            'button:has-text("Не сейчас")', 'button:has-text("Not now")',
            'button:has-text("Позже")', 'button:has-text("Later")',
            
            # Общие кнопки закрытия
            'button[class*="close"]', 'button[class*="dismiss"]',
            'span[class*="close"]', 'div[class*="close"]',
            'svg[class*="close"]', 'a[class*="close"]',
        ]
    
    def _get_popup_hash(self, element: ElementHandle) -> str:
        """Генерация уникального хэша для попапа"""
        try:
            # Используем комбинацию класса, текста и позиции
            class_name = element.get_attribute('class') or ''
            text = element.inner_text()[:50] if element.inner_text else ''
            rect = element.bounding_box() or {}
            position = f"{rect.get('x', 0)},{rect.get('y', 0)}"
            
            hash_str = f"{class_name}_{text}_{position}"
            return hashlib.md5(hash_str.encode()).hexdigest()[:8]
        except:
            return str(id(element))
    
    async def _is_safe_to_close(self, popup: ElementHandle, page_url: str) -> bool:
        """Определить, безопасно ли закрывать этот попап"""
        
        # Проверяем URL страницы
        url_lower = page_url.lower()
        
        # Если это страница логина/регистрации, не закрываем логин-попапы
        if config.skip_login_popups:
            if any(word in url_lower for word in ['login', 'signin', 'auth', 'войти', 'регистрация', 'register']):
                popup_html = await popup.inner_html()[:500].lower()
                if any(word in popup_html for word in ['email', 'пароль', 'password', 'логин', 'username']):
                    print(f"   ⚠️  Пропускаем попап логина на странице входа")
                    return False
        
        # Проверяем содержимое попапа
        try:
            popup_text = (await popup.inner_text()).lower()
            popup_html = (await popup.inner_html()).lower()
            
            # Проверяем опасные ключевые слова
            dangerous_keywords = [
                'пароль', 'password', 'логин', 'login',
                'платеж', 'оплата', 'payment', 'card', 'карта',
                'cvv', 'cvc', 'сvv', 'сvc',
                'удалить', 'delete', 'удаление',
                'подтвердить', 'confirm', 'подтверждение',
                'важные', 'important', 'критич'
            ]
            
            if any(keyword in popup_text for keyword in dangerous_keywords):
                print(f"   ⚠️  Попап содержит опасные ключевые слова")
                return False
            
            # Проверяем наличие форм ввода
            inputs = await popup.query_selector_all('input, textarea, select')
            if len(inputs) > 2:  # Если много полей ввода, возможно это важная форма
                print(f"   ⚠️  Попап содержит {len(inputs)} полей ввода")
                return False
            
        except Exception as e:
            print(f"   ⚠️  Ошибка анализа попапа: {e}")
        
        return True
    
    async def _find_best_close_button(self, popup: ElementHandle) -> Optional[ElementHandle]:
        """Найти лучшую кнопку закрытия в попапе"""
        
        for selector in self.close_button_selectors:
            try:
                buttons = await popup.query_selector_all(selector)
                
                for button in buttons:
                    if await button.is_visible():
                        # Проверяем, что кнопка действительно кликабельна
                        is_disabled = await button.get_attribute('disabled')
                        is_aria_disabled = await button.get_attribute('aria-disabled')
                        
                        if not (is_disabled or is_aria_disabled == 'true'):
                            # Подсвечиваем кнопку для отладки
                            await self.browser.highlight_element(button, color="#ff9900")
                            return button
                            
            except Exception as e:
                continue
        
        return None
    
    async def close_popup(self, popup: ElementHandle, popup_hash: str) -> bool:
        """Закрыть конкретный попап"""
        
        if popup_hash in self.closed_popups:
            return False  # Уже закрывали
        
        try:
            # 1. Ищем кнопку закрытия
            close_button = await self._find_best_close_button(popup)
            
            if close_button:
                # 2. Кликаем по кнопке закрытия
                await close_button.click(force=True)
                await asyncio.sleep(0.3)
                
                # 3. Проверяем, что попап исчез
                if not await popup.is_visible():
                    self.closed_popups.add(popup_hash)
                    self.popup_counter += 1
                    return True
                else:
                    # Попробуем альтернативные методы
                    return await self._try_alternative_close(popup, popup_hash)
            
            else:
                # Если нет кнопки закрытия, пробуем кликнуть вне попапа
                return await self._try_click_outside(popup, popup_hash)
                
        except Exception as e:
            print(f"   ❌ Ошибка закрытия попапа: {e}")
            return False
    
    async def _try_alternative_close(self, popup: ElementHandle, popup_hash: str) -> bool:
        """Альтернативные методы закрытия попапа"""
        
        try:
            # 1. Попробуем Escape
            await self.browser.page.keyboard.press('Escape')
            await asyncio.sleep(0.5)
            
            if not await popup.is_visible():
                self.closed_popups.add(popup_hash)
                return True
            
            # 2. Попробуем кликнуть на backdrop
            backdrops = await self.browser.page.query_selector_all('.modal-backdrop, .modal-overlay, .overlay')
            for backdrop in backdrops:
                if await backdrop.is_visible():
                    await backdrop.click()
                    await asyncio.sleep(0.5)
                    
                    if not await popup.is_visible():
                        self.closed_popups.add(popup_hash)
                        return True
            
            return False
            
        except Exception as e:
            print(f"   ⚠️  Альтернативные методы не сработали: {e}")
            return False
    
    async def _try_click_outside(self, popup: ElementHandle, popup_hash: str) -> bool:
        """Кликнуть вне попапа"""
        try:
            # Получаем координаты попапа
            rect = await popup.bounding_box()
            if rect:
                # Кликаем слева от попапа
                await self.browser.page.mouse.click(rect['x'] - 10, rect['y'] + 10)
                await asyncio.sleep(0.5)
                
                if not await popup.is_visible():
                    self.closed_popups.add(popup_hash)
                    return True
        except:
            pass
        
        return False
    
    async def handle_popups(self) -> int:
        """Основная функция обработки попапов"""
        
        if not config.auto_close_popups:
            return 0
        
        if not self.browser.page:
            return 0
        
        print(f"   🔍 Поиск всплывающих окон...")
        
        popups_closed = 0
        start_time = datetime.now()
        
        # Очищаем историю закрытых попапов для новой страницы
        if self.popup_counter > config.max_popups_per_page:
            self.closed_popups.clear()
            self.popup_counter = 0
        
        # 1. Сначала ищем безопасные попапы
        safe_popups = []
        for selector in self.safe_popup_selectors:
            if popups_closed >= config.max_popups_per_page:
                break
            
            try:
                elements = await self.browser.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        safe_popups.append(element)
            except:
                continue
        
        # 2. Закрываем безопасные попапы
        for popup in safe_popups:
            if popups_closed >= config.max_popups_per_page:
                break
            
            popup_hash = self._get_popup_hash(popup)
            
            if await self._is_safe_to_close(popup, self.browser.page.url):
                if await self.close_popup(popup, popup_hash):
                    popups_closed += 1
                    print(f"   🪟 Закрыто безопасное всплывающее окно ({popups_closed}/{config.max_popups_per_page})")
                    await asyncio.sleep(0.2)  # Небольшая пауза между закрытиями
        
        # 3. Проверяем опасные попапы (только для логирования)
        for selector in self.dangerous_popup_selectors:
            try:
                elements = await self.browser.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        print(f"   ⚠️  Обнаружено важное всплывающее окно: {selector}")
                        # Не закрываем, только логируем
            except:
                continue
        
        # 4. Общие проверки для любых модальных окон
        if popups_closed == 0:
            # Проверяем общие модальные селекторы
            general_selectors = [
                '[role="dialog"]',
                '.modal', '.popup',
                '[aria-modal="true"]',
                '.modal-dialog', '.popup-dialog',
                'div[class*="modal"]', 'div[class*="popup"]',
            ]
            
            for selector in general_selectors:
                if popups_closed >= config.max_popups_per_page:
                    break
                
                try:
                    elements = await self.browser.page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            popup_hash = self._get_popup_hash(element)
                            
                            # Проверяем, что это не важный попап
                            element_text = (await element.inner_text()).lower()
                            if any(word in element_text for word in ['login', 'sign in', 'войти', 'password', 'пароль']):
                                continue
                            
                            if await self.close_popup(element, popup_hash):
                                popups_closed += 1
                                print(f"   🪟 Закрыто общее всплывающее окно")
                                await asyncio.sleep(0.2)
                except:
                    continue
        
        # Логируем результат
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        if popups_closed > 0:
            print(f"   ✅ Закрыто {popups_closed} всплывающих окон за {elapsed:.0f}мс")
        
        return popups_closed


class SPAManager:
    """Менеджер для работы с SPA приложениями"""
    
    def __init__(self, browser_controller):
        self.browser = browser_controller
    
    async def detect_spa_framework(self) -> Optional[str]:
        """Обнаружить фреймворк SPA"""
        if not config.detect_spa_frameworks:
            return None
        
        if not self.browser.page:
            return None
        
        try:
            # Проверяем наличие глобальных объектов фреймворков
            framework_checks = [
                ('react', 'typeof window.React !== "undefined"'),
                ('vue', 'typeof window.Vue !== "undefined"'),
                ('angular', 'typeof window.angular !== "undefined"'),
                ('svelte', 'document.querySelector("[class*=\\"svelte\\"]") !== null'),
                ('nextjs', 'typeof window.__NEXT_DATA__ !== "undefined"'),
                ('nuxt', 'typeof window.__NUXT__ !== "undefined"'),
            ]
            
            for framework, check in framework_checks:
                try:
                    exists = await self.browser.page.evaluate(f"() => {{ return {check}; }}")
                    if exists:
                        print(f"   🎯 Обнаружен SPA фреймворк: {framework.upper()}")
                        return framework
                except:
                    continue
            
            # Проверяем по классам в DOM
            body_class = await self.browser.page.get_attribute('body', 'class') or ''
            html_class = await self.browser.page.get_attribute('html', 'class') or ''
            
            all_classes = f"{body_class} {html_class}".lower()
            
            spa_indicators = ['react', 'vue', 'angular', 'svelte', 'next', 'nuxt']
            for indicator in spa_indicators:
                if indicator in all_classes:
                    print(f"   🎯 Обнаружен SPA фреймворк по классам: {indicator.upper()}")
                    return indicator
            
            return None
            
        except Exception as e:
            print(f"   ⚠️  Ошибка определения SPA фреймворка: {e}")
            return None
    
    async def wait_for_spa_load(self) -> bool:
        """Ожидание загрузки SPA приложения"""
        if not config.wait_for_spa_load:
            return True
        
        if not self.browser.page:
            return False
        
        print(f"   ⏳ Ожидание загрузки SPA...")
        start_time = datetime.now()
        
        try:
            # 1. Ждем, пока страница полностью загрузится
            await self.browser.page.wait_for_load_state('networkidle', timeout=config.spa_load_timeout)
            
            # 2. Ждем, пока исчезнут индикаторы загрузки
            await self._wait_for_loading_indicators()
            
            # 3. Ждем немного для завершения всех анимаций
            await asyncio.sleep(0.5)
            
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            print(f"   ✅ SPA загружено за {elapsed:.0f}мс")
            return True
            
        except Exception as e:
            print(f"   ⚠️  SPA не загрузилось полностью: {e}")
            return False
    
    async def _wait_for_loading_indicators(self):
        """Ожидание исчезновения индикаторов загрузки"""
        loading_selectors = [
            '.loading', '.spinner', '.loader',
            '.progress-bar', '.progress-indicator',
            '.skeleton', '.skeleton-loader',
            '.placeholder', '.shimmer',
        ]
        
        for selector in loading_selectors:
            try:
                elements = await self.browser.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        # Ждем, пока элемент не станет невидимым
                        try:
                            await element.wait_for_element_state('hidden', timeout=2000)
                        except:
                            pass
            except:
                continue


class EnhancedElementDetector:
    """Улучшенный детектор элементов для SPA"""
    
    def __init__(self, browser_controller):
        self.browser = browser_controller
        
    async def find_element_with_context(self, description: str, context: Dict = None) -> Tuple[bool, Any, str]:
        """Найти элемент с учетом контекста"""
        if not config.enhanced_element_detection:
            return await self.browser._basic_element_search(description)
        
        print(f"   🔍 Улучшенный поиск элемента: '{description}'")
        
        strategies = [
            self._try_by_aria_label,
            self._try_by_role,
            self._try_by_text_with_context,
            self._try_by_placeholder,
            self._try_by_test_id,
            self._try_by_class_pattern,
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                success, element, info = await strategy(description, context or {})
                if success:
                    print(f"   ✅ Найден через стратегию {i+1}: {info}")
                    return True, element, info
            except Exception as e:
                continue
        
        return False, None, "Элемент не найден"
    
    async def _try_by_aria_label(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по aria-label"""
        selector = f'[aria-label*="{description}" i]'
        try:
            elements = await self.browser.page.query_selector_all(selector)
            if elements:
                for element in elements:
                    if await element.is_visible():
                        return True, element, f"aria-label: {description}"
        except:
            pass
        return False, None, ""
    
    async def _try_by_role(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по роли"""
        roles = ['button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem']
        for role in roles:
            try:
                element = self.browser.page.get_by_role(role, name=re.compile(re.escape(description), re.IGNORECASE))
                count = await element.count()
                if count > 0:
                    found = await element.first.element_handle()
                    if await found.is_visible():
                        return True, found, f"role={role}"
            except:
                continue
        return False, None, ""
    
    async def _try_by_text_with_context(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по тексту с учетом контекста"""
        # Если есть контекст, ищем элементы в определенной области
        if context and 'page_type' in context:
            if context['page_type'] == 'login':
                # На странице логина ищем элементы в формах
                forms = await self.browser.page.query_selector_all('form')
                for form in forms:
                    try:
                        elements = await form.query_selector_all(f'*:has-text("{description}")')
                        if elements:
                            for element in elements:
                                if await element.is_visible():
                                    return True, element, f"в форме: {description}"
                    except:
                        continue
        
        # Общий поиск по тексту
        try:
            elements = await self.browser.page.query_selector_all(f'*:has-text("{description}")')
            for element in elements:
                if await element.is_visible():
                    return True, element, f"текст: {description}"
        except:
            pass
        
        return False, None, ""
    
    async def _try_by_placeholder(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по placeholder"""
        selector = f'[placeholder*="{description}" i]'
        try:
            elements = await self.browser.page.query_selector_all(selector)
            if elements:
                for element in elements:
                    if await element.is_visible():
                        return True, element, f"placeholder: {description}"
        except:
            pass
        return False, None, ""
    
    async def _try_by_test_id(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по test-id"""
        selectors = [
            f'[data-testid*="{description}" i]',
            f'[data-test*="{description}" i]',
            f'[data-qa*="{description}" i]',
            f'[data-cy*="{description}" i]',
        ]
        
        for selector in selectors:
            try:
                elements = await self.browser.page.query_selector_all(selector)
                if elements:
                    for element in elements:
                        if await element.is_visible():
                            return True, element, f"test-id: {selector}"
            except:
                continue
        
        return False, None, ""
    
    async def _try_by_class_pattern(self, description: str, context: Dict) -> Tuple[bool, Any, str]:
        """Поиск по паттернам в классах"""
        # Преобразуем описание в возможные классы
        class_patterns = [
            description.lower().replace(' ', '-'),
            description.lower().replace(' ', '_'),
            description.lower().replace(' ', ''),
            f'btn-{description.lower().replace(" ", "-")}',
            f'button-{description.lower().replace(" ", "-")}',
            f'link-{description.lower().replace(" ", "-")}',
        ]
        
        for pattern in class_patterns:
            selector = f'.{pattern}'
            try:
                elements = await self.browser.page.query_selector_all(selector)
                if elements:
                    for element in elements:
                        if await element.is_visible():
                            return True, element, f"класс: {pattern}"
            except:
                continue
        
        return False, None, ""


class BrowserController:
    """Контроллер для управления браузером через Playwright"""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_url = ""
        self.last_page_title = ""
        self.last_page_hash = ""
        
        # Инициализация менеджеров
        self.recovery_strategy = RecoveryStrategy(self)
        self.popup_manager = PopupManager(self)
        self.spa_manager = SPAManager(self)
        self.element_detector = EnhancedElementDetector(self)
    
    async def start(self) -> bool:
        """Запустить браузер"""
        try:
            print("🚀 Запуск браузера...")
            self.playwright = await async_playwright().start()
            
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security' if config.headless else '',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-extensions',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--metrics-recording-only',
                '--mute-audio',
                '--no-first-run',
                '--safebrowsing-disable-auto-update',
                '--disable-notifications',
            ]
            
            # Настройки запуска браузера
            launch_args = {
                "headless": config.headless,
                "slow_mo": config.slow_mo,
                "args": browser_args,
                "timeout": config.browser_timeout
            }
            
            # Запускаем браузер
            self.browser = await self.playwright.chromium.launch(**launch_args)
            
            # Создаем контекст
            context_args = {
                "viewport": {'width': config.default_viewport_width, 'height': config.default_viewport_height},
                "user_agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                "ignore_https_errors": True,
                "java_script_enabled": True,
                "bypass_csp": True,
                "locale": "ru-RU",
                "timezone_id": "Europe/Moscow",
            }
            
            self.context = await self.browser.new_context(**context_args)
            
            # Создаем страницу
            self.page = await self.context.new_page()
            
            # Устанавливаем таймауты
            self.page.set_default_timeout(config.browser_timeout)
            self.page.set_default_navigation_timeout(config.browser_timeout)
            
            # Скрипт для маскировки автоматизации
            await self.page.add_init_script("""
                // Убираем webdriver флаг
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Переопределяем permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Добавляем языки
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ru-RU', 'ru', 'en-US', 'en']
                });
                
                // Модифицируем плагины
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [{
                        "0": { type: "application/pdf", suffixes: "pdf", description: "Portable Document Format" },
                        description: "Portable Document Format",
                        filename: "internal-pdf-viewer",
                        length: 1,
                        name: "Chrome PDF Plugin"
                    }]
                });
                
                // Скрываем автоматизацию в консоли
                const originalLog = console.log;
                console.log = function(...args) {
                    if (args.some(arg => typeof arg === 'string' && 
                        (arg.includes('playwright') || arg.includes('automation')))) {
                        return;
                    }
                    originalLog.apply(console, args);
                };
                
                // Скрываем Playwright в свойствах
                window.playwright = undefined;
                window.Playwright = undefined;
            """)
            
            # Создаем папку для скриншотов
            os.makedirs("screenshots", exist_ok=True)
            
            print("✅ Браузер успешно запущен")
            print(f"   🎨 Разрешение: {config.default_viewport_width}x{config.default_viewport_height}")
            print(f"   🪟 Режим: {'Скрытый' if config.headless else 'Видимый'}")
            print(f"   🔄 Система восстановления активна")
            print(f"   🎯 Обнаружение SPA: {'Вкл' if config.wait_for_spa_load else 'Выкл'}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка запуска браузера: {e}")
            print(f"   Проверьте установку Playwright: pip install playwright")
            print(f"   И установите браузеры: playwright install chromium")
            await self.close()
            raise
    
    async def goto(self, url: str) -> Tuple[bool, str]:
        """Перейти по URL"""
        if not self.page:
            raise RuntimeError("Браузер не запущен")
        
        try:
            # Проверяем и нормализуем URL
            if not url.startswith(('http://', 'https://')):
                if url.startswith('www.'):
                    url = 'https://' + url
                else:
                    url = 'https://www.' + url
            
            print(f"   🌐 Переход на: {url[:100]}")
            
            try:
                # Переходим с таймаутом и обработкой ошибок
                response = await self.page.goto(
                    url, 
                    wait_until="domcontentloaded", 
                    timeout=config.browser_timeout,
                    referer="https://www.google.com/"
                )
                
                if response and response.status >= 400:
                    print(f"   ⚠️  HTTP ошибка: {response.status}")
                    if response.status == 404:
                        return False, f"Страница не найдена (404): {url}"
                    elif response.status == 403:
                        return False, f"Доступ запрещен (403): {url}"
                    elif response.status == 500:
                        return False, f"Ошибка сервера (500): {url}"
                
            except Exception as nav_error:
                print(f"   ⚠️  Ошибка навигации: {nav_error}")
                # Пробуем альтернативный подход
                try:
                    await self.page.goto(url, wait_until="load", timeout=15000)
                except:
                    pass
            
            # Ждем загрузки
            await asyncio.sleep(2)
            await self.wait_for_network_idle(3000)
            
            # Обрабатываем SPA приложения
            framework = await self.spa_manager.detect_spa_framework()
            if framework:
                await self.spa_manager.wait_for_spa_load()
            
            # Используем менеджер попапов
            popups_handled = await self.popup_manager.handle_popups()
            if popups_handled > 0:
                print(f"   🪟 Обработано {popups_handled} всплывающих окон")
                await asyncio.sleep(1)
            
            # Обновляем текущий URL
            self.current_url = self.page.url
            
            # Обновляем информацию о странице
            self.last_page_title = await self.page.title()
            self.last_page_hash = await self._get_page_hash()
            
            # Делаем скриншот после перехода
            await self.take_screenshot()
            
            # Проверяем успешность перехода
            if self.page.url == "about:blank":
                print(f"   ⚠️  Страница не загрузилась")
                return False, self.page.url
            
            print(f"   ✅ Успешный переход, текущий URL: {self.current_url[:100]}")
            if framework:
                print(f"   🎯 Тип приложения: SPA ({framework.upper()})")
            
            return True, self.current_url
            
        except Exception as e:
            print(f"   ❌ Ошибка перехода: {e}")
            current_url = self.page.url if self.page else "Нет страницы"
            return False, current_url
    
    async def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        """Ожидание появления элемента с таймаутом"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
            return True
        except Exception as e:
            print(f"   ⏳ Таймаут ожидания элемента {selector}: {e}")
            return False
    
    async def wait_for_network_idle(self, timeout: int = 5000) -> bool:
        """Ожидание завершения сетевых запросов"""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except:
            return False
    
    async def highlight_element(self, element, color: str = "#00ff00", duration: float = 0.5):
        """Визуально подсветить элемент"""
        if not self.page:
            return
        
        try:
            # Сохраняем оригинальный стиль
            original_style = await element.evaluate("""
                element => {
                    return {
                        outline: element.style.outline,
                        outlineOffset: element.style.outlineOffset,
                        transition: element.style.transition,
                        zIndex: element.style.zIndex
                    };
                }
            """)
            
            # Применяем подсветку
            await element.evaluate(f"""
                element => {{
                    element.style.outline = '3px solid {color}';
                    element.style.outlineOffset = '2px';
                    element.style.transition = 'outline 0.3s ease';
                    element.style.zIndex = '9999';
                }}
            """)
            
            # Ждем указанное время
            await asyncio.sleep(duration)
            
            # Восстанавливаем оригинальный стиль
            await element.evaluate("""
                (element, original) => {
                    element.style.outline = original.outline;
                    element.style.outlineOffset = original.outlineOffset;
                    element.style.transition = original.transition;
                    element.style.zIndex = original.zIndex;
                }
            """, original_style)
            
        except Exception as e:
            print(f"   ⚠️  Ошибка подсветки элемента: {e}")
    
    async def take_screenshot(self, filename: str = None) -> Optional[str]:
        """Сделать скриншот текущей страницы"""
        if not self.page:
            return None
        
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"screenshots/screenshot_{timestamp}.png"
            
            os.makedirs("screenshots", exist_ok=True)
            await self.page.screenshot(path=filename, full_page=True)
            print(f"   📸 Скриншот сохранен: {filename}")
            return filename
        except Exception as e:
            print(f"   ⚠️  Ошибка создания скриншота: {e}")
            return None
    
    async def get_page_summary(self) -> Dict:
        """Получить сводную информацию о странице"""
        if not self.page:
            raise RuntimeError("Браузер не запущен")
        
        try:
            # Обрабатываем попапы
            popups_handled = await self.popup_manager.handle_popups()
            
            # Определяем тип SPA
            framework = await self.spa_manager.detect_spa_framework()
            
            # Получаем базовую информацию
            title = await self.page.title()
            url = self.page.url
            
            # Проверяем, изменилась ли страница
            current_hash = await self._get_page_hash()
            page_changed = current_hash != self.last_page_hash
            self.last_page_hash = current_hash
            
            # Получаем интерактивные элементы через JavaScript
            interactive_elements = await self.page.evaluate("""
                () => {
                    const elements = [];
                    const selectors = [
                        'a', 'button', 'input[type="button"]', 'input[type="submit"]',
                        '[role="button"]', '[role="link"]', '[role="tab"]',
                        'input[type="text"]', 'input[type="email"]', 
                        'input[type="password"]', 'input[type="search"]',
                        'textarea', 'select', '[contenteditable="true"]',
                        'input:not([type])', 'div[onclick]', 'span[onclick]',
                        '[data-testid]', '[data-qa]', '[data-test]',
                        '[role="menuitem"]', '[role="option"]', '[role="radio"]',
                        '[role="checkbox"]', '[type="radio"]', '[type="checkbox"]'
                    ];
                    
                    // Собираем видимые элементы
                    selectors.forEach(selector => {
                        const nodeList = document.querySelectorAll(selector);
                        for (const el of nodeList) {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            
                            // Проверяем видимость
                            if (rect.width > 0 && rect.height > 0 &&
                                style.display !== 'none' &&
                                style.visibility !== 'hidden' &&
                                style.opacity !== '0') {
                                
                                // Получаем текст элемента
                                let text = '';
                                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
                                    text = el.placeholder || el.value || el.name || el.id || el.getAttribute('aria-label') || '';
                                } else {
                                    text = el.innerText?.trim() || 
                                           el.textContent?.trim() || 
                                           el.getAttribute('aria-label') || 
                                           el.title || 
                                           el.alt || 
                                           el.getAttribute('data-text') || '';
                                }
                                
                                // Фильтруем пустые или слишком длинные тексты
                                if (text && text.length > 0 && text.length < 100) {
                                    const isInput = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT';
                                    const isButton = el.tagName === 'BUTTON' || 
                                                    el.getAttribute('role') === 'button' ||
                                                    (el.tagName === 'INPUT' && 
                                                     (el.type === 'button' || el.type === 'submit')) ||
                                                    el.hasAttribute('onclick');
                                    const isLink = el.tagName === 'A' || el.getAttribute('role') === 'link';
                                    const isCheckbox = el.type === 'checkbox' || el.getAttribute('role') === 'checkbox';
                                    const isRadio = el.type === 'radio' || el.getAttribute('role') === 'radio';
                                    
                                    elements.push({
                                        "text": text.replace(/\\n/g, ' ').substring(0, 80),
                                        "tag": el.tagName.toLowerCase(),
                                        "type": el.type || '',
                                        "is_input": isInput,
                                        "is_button": isButton,
                                        "is_link": isLink,
                                        "is_checkbox": isCheckbox,
                                        "is_radio": isRadio,
                                        "id": el.id || '',
                                        "class": el.className.substring(0, 30) || '',
                                        "visible": true,
                                        "coordinates": {
                                            "x": Math.round(rect.x),
                                            "y": Math.round(rect.y),
                                            "width": Math.round(rect.width),
                                            "height": Math.round(rect.height)
                                        }
                                    });
                                }
                            }
                        }
                    });
                    
                    // Удаляем дубликаты по тексту и координатам
                    const uniqueElements = [];
                    const seenKeys = new Set();
                    
                    for (const elem of elements) {
                        const key = `${elem.text.toLowerCase().trim()}_${elem.coordinates.x}_${elem.coordinates.y}`;
                        if (key && !seenKeys.has(key) && elem.text.length > 1) {
                            seenKeys.add(key);
                            uniqueElements.push(elem);
                        }
                    }
                    
                    // Сортируем по позиции на странице (сверху вниз, слева направо)
                    uniqueElements.sort((a, b) => {
                        if (a.coordinates.y !== b.coordinates.y) {
                            return a.coordinates.y - b.coordinates.y;
                        }
                        return a.coordinates.x - b.coordinates.x;
                    });
                    
                    return uniqueElements.slice(0, 50); // Ограничиваем количество
                }
            """)
            
            # Анализируем страницу для определения типа
            page_type = "unknown"
            page_url_lower = url.lower()
            page_title_lower = title.lower()
            
            if any(word in page_url_lower or word in page_title_lower 
                   for word in ["login", "signin", "auth", "account", "вход", "войти", "log in"]):
                page_type = "login"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["checkout", "cart", "payment", "pay", "корзин", "оплат", "buy", "purchase", "order"]):
                page_type = "payment"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["register", "signup", "регистрация", "create", "sign up", "signup"]):
                page_type = "registration"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["search", "поиск", "find", "google", "yandex", "bing"]):
                page_type = "search"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["social", "facebook", "twitter", "vk", "instagram", "tiktok", "linkedin"]):
                page_type = "social"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["email", "mail", "gmail", "почта", "outlook", "yahoo"]):
                page_type = "email"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["news", "новости", "article", "статья", "blog", "блог"]):
                page_type = "news"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["settings", "настройки", "profile", "профиль", "account", "аккаунт"]):
                page_type = "settings"
            elif any(word in page_url_lower or word in page_title_lower 
                     for word in ["dashboard", "панель", "admin", "админ", "control"]):
                page_type = "dashboard"
            
            return {
                'title': title or 'Без заголовка',
                'url': url,
                'page_type': page_type,
                'is_spa': framework is not None,
                'spa_framework': framework,
                'interactive_elements': interactive_elements,
                'element_count': len(interactive_elements),
                'page_changed': page_changed,
                'popups_handled': popups_handled
            }
            
        except Exception as e:
            print(f"❌ Ошибка получения информации о странице: {e}")
            return {
                'title': 'Ошибка',
                'url': self.page.url if self.page else '',
                'page_type': 'error',
                'is_spa': False,
                'spa_framework': None,
                'interactive_elements': [],
                'element_count': 0,
                'page_changed': False,
                'popups_handled': 0
            }
    
    async def click_element(self, description: str) -> Tuple[bool, str]:
        """Кликнуть на элемент по текстовому описанию (с улучшенным поиском)"""
        return await self.click_element_with_feedback(description)
    
    async def click_element_with_feedback(self, description: str) -> Tuple[bool, str]:
        """Кликнуть на элемент с визуальной обратной связью"""
        print(f"   🖱️  Поиск элемента: '{description}'")
        
        # Обрабатываем всплывающие окна
        popups_handled = await self.popup_manager.handle_popups()
        if popups_handled > 0:
            print(f"   🪟 Обработано {popups_handled} всплывающих окон")
            await asyncio.sleep(1)
        
        search_text = description.strip(' "\':').strip()
        
        if not search_text:
            return False, "Пустое описание элемента"
        
        # Используем улучшенный детектор элементов
        if config.enhanced_element_detection:
            page_info = await self.get_page_summary()
            context = {
                'page_type': page_info.get('page_type', 'unknown'),
                'is_spa': page_info.get('is_spa', False),
                'spa_framework': page_info.get('spa_framework')
            }
            
            success, element, element_info = await self.element_detector.find_element_with_context(
                search_text, context
            )
            
            if success:
                try:
                    # Подсвечиваем элемент
                    await self.highlight_element(element, color="#00ff00")
                    
                    # Прокручиваем к элементу
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Проверяем видимость
                    if not await element.is_visible():
                        print(f"   ⚠️  Элемент стал невидимым после прокрутки")
                        # Пробуем стандартные методы
                        return await self._try_standard_click(search_text)
                    
                    # Проверяем, что элемент не перекрыт
                    try:
                        is_hidden = await element.evaluate("""
                            element => {
                                const rect = element.getBoundingClientRect();
                                const centerX = rect.left + rect.width / 2;
                                const centerY = rect.top + rect.height / 2;
                                const topElement = document.elementFromPoint(centerX, centerY);
                                return topElement !== element && !element.contains(topElement);
                            }
                        """)
                        
                        if is_hidden:
                            print(f"   ⚠️  Элемент перекрыт другим элементом")
                            # Пробуем кликнуть с force
                            await element.click(force=True, timeout=5000)
                        else:
                            await element.click(force=False, timeout=5000)
                    except:
                        await element.click(force=True, timeout=5000)
                    
                    # Ждем после клика
                    await asyncio.sleep(1.5)
                    
                    # Проверяем, не открылись ли новые окны/вкладки
                    if len(self.page.context.pages) > 1:
                        print(f"   🔄 Обнаружена новая вкладка")
                        # Переключаемся на новую вкладку
                        new_page = self.page.context.pages[-1]
                        await new_page.bring_to_front()
                        self.page = new_page
                    
                    print(f"   ✅ Успешный клик {element_info}")
                    
                    # Делаем скриншот после действия
                    await self.take_screenshot()
                    
                    return True, element_info
                    
                except Exception as e:
                    print(f"   ⚠️  Ошибка клика через улучшенный детектор: {e}")
                    # Пробуем стандартные методы
        
        # Стандартные методы поиска
        return await self._try_standard_click(search_text)
    
    async def _try_standard_click(self, search_text: str) -> Tuple[bool, str]:
        """Стандартные методы поиска и клика"""
        strategies = [
            # 1. Точное совпадение текста
            lambda: self.page.get_by_text(search_text, exact=True),
            
            # 2. Частичное совпадение текста
            lambda: self.page.get_by_text(search_text, exact=False),
            
            # 3. Поиск по роли button
            lambda: self.page.get_by_role("button", name=re.compile(re.escape(search_text), re.IGNORECASE)),
            
            # 4. Поиск по роли link
            lambda: self.page.get_by_role("link", name=re.compile(re.escape(search_text), re.IGNORECASE)),
            
            # 5. Поиск по placeholder
            lambda: self.page.get_by_placeholder(search_text),
            
            # 6. Поиск по label
            lambda: self.page.get_by_label(search_text),
            
            # 7. Поиск по title
            lambda: self.page.locator(f'[title*="{search_text}"]'),
            
            # 8. Поиск по aria-label
            lambda: self.page.locator(f'[aria-label*="{search_text}"]'),
            
            # 9. Поиск по value для input
            lambda: self.page.locator(f'input[value*="{search_text}"]'),
            
            # 10. Поиск по data-* атрибутам
            lambda: self.page.locator(f'[data-testid*="{search_text}"]'),
            lambda: self.page.locator(f'[data-qa*="{search_text}"]'),
            lambda: self.page.locator(f'[data-test*="{search_text}"]'),
            lambda: self.page.locator(f'[data-id*="{search_text}"]'),
            
            # 11. Поиск по классу (последний вариант)
            lambda: self.page.locator(f'.{search_text.replace(" ", ".").replace("-", ".")}'),
        ]
        
        clicked = False
        element_info = ""
        
        for i, strategy in enumerate(strategies):
            try:
                element = strategy()
                count = await element.count()
                
                if count > 0:
                    found_element = await element.first.element_handle()
                    element_info = f"(стратегия {i+1}, найдено: {count})"
                    
                    # Подсвечиваем элемент
                    await self.highlight_element(found_element, color="#00ff00")
                    
                    # Прокручиваем к элементу
                    await element.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Проверяем видимость
                    if not await element.first.is_visible():
                        print(f"   ⚠️  Элемент стал невидимым после прокрутки")
                        continue
                    
                    # Проверяем, что элемент не перекрыт
                    try:
                        is_hidden = await element.first.evaluate("""
                            element => {
                                const rect = element.getBoundingClientRect();
                                const centerX = rect.left + rect.width / 2;
                                const centerY = rect.top + rect.height / 2;
                                const topElement = document.elementFromPoint(centerX, centerY);
                                return topElement !== element && !element.contains(topElement);
                            }
                        """)
                        
                        if is_hidden:
                            print(f"   ⚠️  Элемент перекрыт другим элементом")
                            # Пробуем кликнуть с force
                            await element.first.click(force=True, timeout=5000)
                        else:
                            await element.first.click(force=False, timeout=5000)
                    except:
                        await element.first.click(force=True, timeout=5000)
                    
                    # Ждем после клика
                    await asyncio.sleep(1.5)
                    
                    # Проверяем, не открылись ли новые окны/вкладки
                    if len(self.page.context.pages) > 1:
                        print(f"   🔄 Обнаружена новая вкладка")
                        # Переключаемся на новую вкладку
                        new_page = self.page.context.pages[-1]
                        await new_page.bring_to_front()
                        self.page = new_page
                    
                    clicked = True
                    print(f"   ✅ Успешный клик {element_info}")
                    
                    # Делаем скриншот после действия
                    await self.take_screenshot()
                    
                    break
                    
            except Exception as e:
                if i == len(strategies) - 1:
                    print(f"   ⚠️  Стратегия {i+1} не сработала: {e}")
                continue
        
        # Если элемент не найден стандартными способами
        if not clicked:
            clicked, element_info = await self._try_alternative_search(search_text)
        
        return clicked, element_info
    
    async def _try_alternative_search(self, search_text: str) -> Tuple[bool, str]:
        """Альтернативные методы поиска элемента"""
        print(f"   🔍 Пробую альтернативный поиск: '{search_text}'")
        
        alternative_selectors = [
            f'button:has-text("{search_text}")',
            f'input[type="button"][value*="{search_text}"]',
            f'input[type="submit"][value*="{search_text}"]',
            f'a:has-text("{search_text}")',
            f'div:has-text("{search_text}")',
            f'span:has-text("{search_text}")',
            f'p:has-text("{search_text}")',
            f'li:has-text("{search_text}")',
            f'*[onclick*="{search_text.lower()}"]',
            f'*:contains("{search_text}")',
            f'[class*="{search_text.lower().replace(" ", "")}"]',
            f'[id*="{search_text.lower().replace(" ", "")}"]',
            f'[name*="{search_text.lower().replace(" ", "")}"]',
            f'[for*="{search_text.lower().replace(" ", "")}"]',
        ]
        
        for selector in alternative_selectors:
            try:
                element = self.page.locator(selector)
                count = await element.count()
                if count > 0:
                    found_element = await element.first.element_handle()
                    await self.highlight_element(found_element, color="#ff9900")
                    await element.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Проверяем, можно ли кликнуть
                    is_disabled = await element.first.evaluate("""
                        element => element.disabled || element.getAttribute('aria-disabled') === 'true'
                    """)
                    
                    if is_disabled:
                        print(f"   ⚠️  Элемент disabled, пропускаем")
                        continue
                    
                    await element.first.click(force=True, timeout=5000)
                    await asyncio.sleep(1.5)
                    print(f"   ✅ Найден через альтернативный поиск: {selector}")
                    return True, f"(альтернативный: {selector})"
            except Exception as e:
                print(f"   ⚠️  Ошибка с селектором {selector}: {e}")
                continue
        
        return False, "Элемент не найден"
    
    async def type_text(self, text: str) -> Tuple[bool, bool]:
        """Ввести текст в активное поле"""
        if not self.page:
            raise RuntimeError("Браузер не запущен")
        
        is_password_field = False
        print(f"   ⌨️  Ввод текста: '{text[:30]}{'...' if len(text) > 30 else ''}'")
        
        try:
            # Обрабатываем попапы перед вводом
            await self.popup_manager.handle_popups()
            
            # Сначала проверяем поля пароля
            password_fields = await self.page.query_selector_all('input[type="password"]')
            
            if password_fields:
                is_password_field = True
                for field in password_fields:
                    try:
                        if await field.is_visible():
                            await self.highlight_element(field, color="#ff6600")
                            await field.scroll_into_view_if_needed()
                            await field.click()
                            await field.fill('')
                            await field.type(text, delay=30)
                            print(f"   🔐 Ввод в поле пароля")
                            return True, is_password_field
                    except:
                        continue
            
            # Затем проверяем другие поля ввода
            input_selectors = [
                'input[type="text"]:not([readonly])',
                'input[type="email"]', 
                'input[type="search"]',
                'input:not([type]):not([readonly])',
                'textarea:not([readonly])',
                '[contenteditable="true"]',
                '[role="textbox"]',
                '[role="combobox"]',
                '[aria-label*="search" i]',
                '[placeholder*="search" i]',
                '[name*="search" i]',
            ]
            
            for selector in input_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            # Подсвечиваем поле
                            await self.highlight_element(element, color="#0099ff")
                            
                            # Прокручиваем к элементу
                            await element.scroll_into_view_if_needed()
                            
                            # Ждем немного
                            await asyncio.sleep(0.2)
                            
                            # Кликаем и очищаем
                            await element.click()
                            await element.fill('')
                            
                            # Вводим текст с задержкой
                            await element.type(text, delay=30)
                            
                            # Проверяем, что текст введен
                            value = await element.input_value()
                            if value == text or (len(text) > 20 and text[:20] in value):
                                print(f"   ✅ Текст введен в поле {selector}")
                                return True, is_password_field
                except Exception as e:
                    print(f"   ⚠️  Ошибка с селектором {selector}: {e}")
                    continue
            
            # Если не нашли подходящее поле, пытаемся ввести через активный элемент
            try:
                print(f"   ℹ️  Пробую ввод через активный элемент...")
                
                # Кликаем на body чтобы активировать страницу
                await self.page.click('body')
                await asyncio.sleep(0.1)
                
                # Вводим текст
                await self.page.keyboard.type(text, delay=30)
                
                # Проверяем, есть ли поле с введенным текстом
                fields_with_text = await self.page.query_selector_all(f'input[value*="{text[:10]}"], textarea')
                if fields_with_text:
                    print(f"   ✅ Текст введен через клавиатуру")
                    return True, is_password_field
                else:
                    print(f"   ⚠️  Текст введен, но не найден в полях")
                    return True, is_password_field
                    
            except Exception as e:
                print(f"   ❌ Не удалось ввести текст через клавиатуру: {e}")
                return False, is_password_field
                
        except Exception as e:
            print(f"   ❌ Ошибка ввода текста: {e}")
            return False, is_password_field
    
    async def scroll_down(self, pixels: int = 500) -> bool:
        """Прокрутить страницу вниз"""
        if not self.page:
            raise RuntimeError("Браузер не запущен")
        
        try:
            print(f"   📜 Прокрутка на {pixels}px")
            
            # Прокручиваем с анимацией
            await self.page.evaluate(f"""
                (pixels) => {{
                    window.scrollBy({{
                        top: pixels,
                        behavior: 'smooth'
                    }});
                }}
            """, pixels)
            
            # Ждем завершения прокрутки
            await asyncio.sleep(1)
            
            # Проверяем, можно ли прокрутить дальше
            can_scroll_more = await self.page.evaluate("""
                () => {
                    return window.innerHeight + window.scrollY < document.body.scrollHeight - 100;
                }
            """)
            
            if not can_scroll_more:
                print(f"   ⚠️  Достигнут конец страницы")
            
            return True
            
        except Exception as e:
            print(f"   ❌ Ошибка прокрутки: {e}")
            return False
    
    async def get_full_page_text(self) -> str:
        """Получить весь текст страницы (для анализа контекста)"""
        if not self.page:
            return ""
        
        try:
            text = await self.page.evaluate("""
                () => {
                    // Функция для извлечения видимого текста
                    function extractVisibleText(node) {
                        let text = '';
                        
                        // Рекурсивно обходим дерево
                        const walker = document.createTreeWalker(
                            node,
                            NodeFilter.SHOW_TEXT,
                            {
                                acceptNode: function(node) {
                                    // Пропускаем скрытые элементы
                                    const parent = node.parentElement;
                                    if (!parent) return NodeFilter.FILTER_REJECT;
                                    
                                    const style = window.getComputedStyle(parent);
                                    if (parent.offsetParent === null ||
                                        style.display === 'none' ||
                                        style.visibility === 'hidden' ||
                                        style.opacity === '0' ||
                                        parent.hidden ||
                                        parent.closest('[hidden]')) {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    // Пропускаем пустой текст
                                    const nodeText = node.textContent.trim();
                                    if (nodeText.length === 0) {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    // Пропускаем скрипты и стили
                                    if (parent.tagName === 'SCRIPT' || 
                                        parent.tagName === 'STYLE' ||
                                        parent.tagName === 'NOSCRIPT' ||
                                        parent.tagName === 'SVG' ||
                                        parent.tagName === 'PATH') {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    // Пропускаем слишком маленькие элементы (иконки и т.д.)
                                    const rect = parent.getBoundingClientRect();
                                    if (rect.width < 5 && rect.height < 5) {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    return NodeFilter.FILTER_ACCEPT;
                                }
                            }
                        );
                        
                        let currentNode;
                        while (currentNode = walker.nextNode()) {
                            text += currentNode.textContent.trim() + ' ';
                        }
                        
                        return text.replace(/\\s+/g, ' ').trim();
                    }
                    
                    return extractVisibleText(document.body);
                }
            """)
            
            return text[:3000]  # Ограничиваем объем
            
        except Exception as e:
            print(f"❌ Ошибка извлечения текста: {e}")
            return ""
    
    async def get_current_url(self) -> str:
        """Получить текущий URL"""
        if self.page:
            try:
                return self.page.url
            except:
                return ""
        return ""
    
    async def close(self):
        """Закрыть браузер"""
        try:
            # Сохраняем отчет о восстановлениях
            if hasattr(self, 'recovery_strategy'):
                report = self.recovery_strategy.get_recovery_report()
                os.makedirs("logs", exist_ok=True)
                with open("logs/recovery_report.json", 'w', encoding='utf-8') as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                print(f"📊 Отчет о восстановлениях сохранен")
            
            if self.page:
                try:
                    await self.page.close()
                except:
                    pass
                self.page = None
            if self.context:
                try:
                    await self.context.close()
                except:
                    pass
                self.context = None
            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
                self.browser = None
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
                self.playwright = None
            
            print("👋 Браузер закрыт")
            
        except Exception as e:
            print(f"⚠️  Ошибка при закрытии браузера: {e}")

    async def _get_page_hash(self) -> str:
        """Получить хэш содержимого страницы для определения изменений"""
        if not self.page:
            return ""
        
        try:
            content = await self.page.content()
            # Используем упрощенный хэш
            return str(hash(content[:1000]))
        except:
            return ""

    async def _basic_element_search(self, description: str) -> Tuple[bool, Any, str]:
        """Базовая поиск элемента (для обратной совместимости)"""
        try:
            elements = await self.page.query_selector_all(f'*:has-text("{description}")')
            for element in elements:
                if await element.is_visible():
                    return True, element, f"базовый поиск: {description}"
        except:
            pass
        return False, None, ""