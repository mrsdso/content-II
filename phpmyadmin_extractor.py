import requests
import re
from bs4 import BeautifulSoup
import urllib.parse
import sys

class PhpMyAdminExtractor:
    def __init__(self, base_url, username, password): 
        self.base_url = base_url.rstrip('/') #
        self.username = username 
        self.password = password 
        self.session = requests.Session() # Создаем сессию
        self.session.headers.update({ # Установка заголовков
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' 
        })
        self.token = None
        
    def get_login_page(self): # Получить страницу авторизации и извлечь токен
        print("Подключение к phpMyAdmin...")
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            token_input = soup.find('input', {'name': 'token'})
            if token_input:
                self.token = token_input.get('value')
                
            return True
        # Если возникла ошибка, выводим сообщение    
        except requests.RequestException as e:
            print(f"Ошибка подключения: {e}")
            return False
    
    def login(self): # Авторизация в phpMyAdmin
        print("Авторизация...")
        # Попытка авторизации с разными данными
        login_variants = [
            {
                'pma_username': self.username,
                'pma_password': self.password,
                'server': '1',
                'target': 'index.php',
                'lang': 'en'
            },
            {
                'pma_username': self.username,
                'pma_password': self.password,
                'server': '1'
            }
        ]
        
        for login_data in login_variants: # Попытка авторизации с разными данными
            if self.token:
                login_data['token'] = self.token
            # Попытка авторизации    
            try:
                response = self.session.post(
                    f"{self.base_url}/index.php",
                    data=login_data,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                response_text = response.text.lower()
                # Проверка успешной авторизации
                if 'access denied' in response_text: # Если ошибка доступа, пробуем другую авторизацию
                    continue
                elif ('database' in response_text or 'table' in response_text or 
                      'phpmyadmin' in response_text) and 'login' not in response.url:
                    print("Авторизация успешна")
                    return True
                  
            except requests.RequestException:
                continue
        
        print("Ошибка авторизации")
        return False
    
    def get_database_token(self): # Получить токен для работы с базой данных
        try:
            response = self.session.get(f"{self.base_url}/index.php?route=/database/structure&db=testDB")
            soup = BeautifulSoup(response.text, 'html.parser')
            # Поиск токена
            token_input = soup.find('input', {'name': 'token'})
            if token_input:
                self.token = token_input.get('value')
              
            return True
        # Если возникла ошибка, пробуем SQL-запрос    
        except Exception:
            return True
        
    def extract_users_data(self): # Извлечение данных из таблицы users
        print("Извлечение данных из таблицы users...")
        # Если токен уже получен, используем его
        try:
            self.get_database_token()
            # Параметры запроса для извлечения данных
            params = {
                'route': '/sql',
                'db': 'testDB',
                'table': 'users',
                'sql_query': 'SELECT * FROM `users`',
                'session_max_rows': 'all'
            }
            # Если есть токен, добавляем его
            if self.token:
                params['token'] = self.token
            # Формируем URL с параметрами
            url = f"{self.base_url}/index.php?" + urllib.parse.urlencode(params)
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # Поиск таблицы с данными
            table_selectors = [
                'table.table_results',
                'table[id*="table_results"]',
                'table.data',
                'table.table',
                '.sqlOuter table',
                '#page_content table'
            ]
            # Попытка найти таблицу с данными
            data_table = None
            for selector in table_selectors:
                data_table = soup.select_one(selector)
                if data_table:
                    break
            # Если таблица не найдена, пробуем SQL-запрос
            if not data_table:
                return self.extract_via_sql()
            # Извлекаем заголовки
            headers = []
            header_row = data_table.find('tr')
            if header_row:
                for th in header_row.find_all(['th', 'td']):
                    text = th.get_text(strip=True)
                    if text and text not in ['Edit', 'Copy', 'Delete', 'Action', '', 'С']:
                        headers.append(text)
            # Извлекаем данные
            rows = []
            for tr in data_table.find_all('tr')[1:]:
                row = []
                for td in tr.find_all(['td', 'th']):
                    # Пропускаем ячейки с кнопками действий
                    if td.find('a') or td.find('button') or td.find('input'):
                        if any(keyword in str(td).lower() for keyword in ['edit', 'delete', 'copy', 'action']):
                            continue
                    
                    row.append(td.get_text(strip=True))
                # Пропускаем пустые строки
                if row and any(cell.strip() for cell in row):
                    row = row[:len(headers)] if headers else row
                    rows.append(row)
            # Если данные не найдены, пробуем SQL-запрос
            if not rows:
                return self.extract_via_sql()
            # Печатаем данные
            self.print_table_data(headers, rows)
            return True
        # Если возникла ошибка, пробуем SQL-запрос    
        except Exception:
            return self.extract_via_sql()
        
    # Извлечение данных с помощью SQL-запроса
    def extract_via_sql(self):
        try:
            sql_data = {
                'db': 'testDB',
                'sql_query': 'SELECT * FROM users',
                'show_query': '1',
                'format': 'html'
            }
            # Если есть токен, добавляем его
            if self.token:
                sql_data['token'] = self.token
            # Выполняем SQL-запрос
            response = self.session.post(
                f"{self.base_url}/index.php?route=/sql",
                data=sql_data
            )
            response.raise_for_status()
            # Парсим ответ
            soup = BeautifulSoup(response.text, 'html.parser')
            tables = soup.find_all('table')
            # Поиск таблицы с данными
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) > 1:
                    # Извлекаем заголовки
                    headers = []
                    header_row = rows[0]
                    for th in header_row.find_all(['th', 'td']):
                        text = th.get_text(strip=True)
                        if text and text not in ['Action', 'Edit', 'Copy', 'Delete', 'С']:
                            headers.append(text)
                    # Извлекаем данные
                    data_rows = []
                    for tr in rows[1:]:
                        row = []
                        cells = tr.find_all(['td', 'th'])
                        # Пропускаем ячейки с кнопками действий
                        for cell in cells:
                            if not cell.find('a') and not cell.find('button'):
                                text = cell.get_text(strip=True)
                                row.append(text)
                        # Пропускаем пустые строки
                        if row and any(cell.strip() for cell in row):
                            row = row[:len(headers)] if headers else row
                            data_rows.append(row)
                    # Если данные найдены, печатаем их
                    if data_rows and headers:
                        self.print_table_data(headers, data_rows)
                        return True
            # Если таблица не найдена, пробуем SQL-запрос
            return False
        # Если возникла ошибка, выводим сообщение    
        except Exception:
            return False
        
    # Печать данных таблицы
    def print_table_data(self, headers, rows):
        print("\n" + "="*80)
        print("СОДЕРЖИМОЕ ТАБЛИЦЫ USERS ИЗ БАЗЫ ДАННЫХ testDB")
        print("="*80)
        # Если нет данных, выводим сообщение
        if not headers or not rows:
            print("Нет данных для отображения")
            return
        
        # Вычисляем ширину столбцов
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(str(header))
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(min(max_width + 2, 30))
        
        # Выводим заголовки
        header_line = "|"
        separator_line = "|"
        for i, header in enumerate(headers):
            header_line += f" {str(header):<{col_widths[i]-1}}|"
            separator_line += "-" * col_widths[i] + "|"
        # Выводим заголовки и разделитель
        print(header_line)
        print(separator_line)
        
        # Выводим данные
        for row in rows:
            row_line = "|"
            for i in range(len(headers)):
                value = str(row[i]) if i < len(row) else ""
                if len(value) > col_widths[i] - 2:
                    value = value[:col_widths[i]-5] + "..."
                row_line += f" {value:<{col_widths[i]-1}}|"
            print(row_line)
        # Выводим количество записей
        print("="*80)
        print(f"Всего записей: {len(rows)}")
        
    # Главный метод запуска извлечения данных
    def run(self):
        """Главный метод запуска извлечения данных"""
        print("phpMyAdmin Data Extractor")
        print("-" * 50)
        # Проверяем подключение к phpMyAdmin
        if not self.get_login_page():
            return False
        # Выполняем авторизацию
        if not self.login():
            return False
        # Извлекаем данные из таблицы users
        if not self.extract_users_data():
            print("Не удалось извлечь данные")
            return False
        # Печатаем сообщение об успешном завершении
        print("\nИзвлечение данных завершено успешно!")
        return True


def main(): # Главная функция
    BASE_URL = "http://185.244.219.162/phpmyadmin"
    USERNAME = "test"
    PASSWORD = "JHFBdsyf2eg8*"
    
    print("Извлечение данных из phpMyAdmin")
    print(f"Сервер: {BASE_URL}")
    print(f"База данных: testDB")
    print(f"Таблица: users")
    print()
    
    extractor = PhpMyAdminExtractor(BASE_URL, USERNAME, PASSWORD)
    # Проверяем подключение к phpMyAdmin
    try:
        success = extractor.run()
        sys.exit(0 if success else 1)
    # Если возникла ошибка, выводим сообщение        
    except KeyboardInterrupt:
        print("\n\nПрерывание выполнения")
        sys.exit(1)
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
        sys.exit(1)

# Если этот файл запущен напрямую, вызываем main()
if __name__ == "__main__":
    main()
