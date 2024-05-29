import json
import re
import os
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementNotInteractableException, WebDriverException, InvalidSessionIdException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from bs4 import BeautifulSoup
from markdownify import markdownify as md
import pandas as pd

# Настройки для ChromeDriver
options = webdriver.ChromeOptions()
options.add_argument("user-agent=Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:84.0) Gecko/20100101 Firefox/84.0")
options.add_argument("--disable-blink-features=AutomationControlled")

# Отключение загрузки изображений
prefs = {
    "profile.managed_default_content_settings.images": 2
}
options.add_experimental_option("prefs", prefs)
s = Service(executable_path="C:\\chromedriver\\chromedriver.exe")
driver = webdriver.Chrome(service=s, options=options)


def clean_markdown(text):
    """Очистка маркдауна от изображений и ссылок"""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'<h[1-6]>(.*?)<\/h[1-6]>', r'### \1', text)
    return text

def extract_domain(url):
    """Извлечение домена из URL"""
    parsed_url = urlparse(url)
    return parsed_url.netloc

def parse_article(url, driver, max_articles=1):
    articles_data = []
    parsed_titles = set()
    article_counter = 0

    try:
        driver.get(url)
        # Ожидание 4 секунд после загрузки главной страницы
        time.sleep(1)
        while True:
            # Ждем загрузки статей на странице
            WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.card-news')))

            # Получаем все статьи на странице
            article_elements = driver.find_elements(By.CSS_SELECTOR, '.card-news')
            article_links = [element.get_attribute('href') for element in article_elements]
            article_links = list(dict.fromkeys(article_links))  # Убираем дублирующиеся ссылки

            for article_link in article_links:
                if max_articles is not None and article_counter >= max_articles:
                    print(f"Достигнуто максимальное количество статей: {max_articles}. Парсинг завершен.")
                    return articles_data

                # Открываем статью в новой вкладке
                driver.execute_script("window.open(arguments[0], '_blank');", article_link)
                driver.switch_to.window(driver.window_handles[-1])

                try:
                    # Ждем загрузки заголовка статьи
                    WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'h1')))
                    
                    title_element = driver.find_element(By.CSS_SELECTOR, 'h1')
                    title = title_element.text.strip()

                    if title in parsed_titles:
                        driver.close()  # Закрываем вкладку с текущей статьей
                        driver.switch_to.window(driver.window_handles[0])  # Переключаемся обратно на основную вкладку
                        continue

                    content_element = driver.find_element(By.CSS_SELECTOR, '.single_content')

                   # Получаем содержимое статьи без указанных блоков
                    content_html = ""
                    for child in BeautifulSoup(content_element.get_attribute('outerHTML'), 'html.parser').find('div', class_='single_content').find_all(recursive=False):
                        if not child.find(class_='single_subheader') and not child.find(class_='single_date') and child.name != 'h1':
                            content_html += str(child)
                    content_html = content_html.strip()

                    # Получаем lead_html
                    lead_element = driver.find_element(By.CSS_SELECTOR, '.single_subheader') if driver.find_elements(By.CSS_SELECTOR, '.single_subheader') else None
                    publication_date_element = driver.find_element(By.CSS_SELECTOR, '.single_date') if driver.find_elements(By.CSS_SELECTOR, '.single_date') else None

                    lead_html = lead_element.get_attribute('innerHTML') if lead_element else ''
                    publication_date = publication_date_element.get_attribute('innerHTML') if publication_date_element else ''

                    # Игнорируем содержимое тега single_views внутри тега single_date
                    publication_date = re.sub(r'<span[^>]*class="single_views"[^>]*>.*?</span>', '', publication_date)

                    # Удаляем строки, содержащие title, lead_html и publication_date из content_html
                    content_html = re.sub(fr'<h1[^>]*>{re.escape(title)}</h1>', '', content_html, flags=re.IGNORECASE)
                    content_html = re.sub(re.escape(lead_html), '', content_html)
                    content_html = re.sub(re.escape(publication_date), '', content_html)

                    # Удаляем пустые теги single_subheader и single_date
                    content_html = re.sub(r'<span class="single_subheader"></span>', '', content_html)
                    # Удаляем тег <div class="single_date"> и его содержимое из content_html
                    content_html = re.sub(r'<div class="single_date"[^>]*>[\s\S]*?</div>', '', content_html)




                    # Извлекаем дополнительные данные
                    domain = extract_domain(article_link)
                    try:
                        content_type = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:type"]').get_attribute('content')
                    except NoSuchElementException:
                        content_type = 'unknown'

                    try:
                        meta_element = driver.find_element(By.CSS_SELECTOR, '.single_date')
                        publication_date = meta_element.text.split('\n')[-1].strip()  # Извлекаем дату публикации
                        
                        # Удаляем publication_date из content_html
                        content_html = re.sub(re.escape(publication_date), '', content_html)
                    except NoSuchElementException:
                        publication_date = 'unknown'

                    # Преобразуем HTML в Markdown
                    content_markdown = md(content_html)

                    h1 = title
                    lead_markdown = md(lead_html)

                    # Сохраняем данные в словарь
                    article_data = {
                        'domain': domain,
                        'url': article_link,
                        'content_type': content_type,
                        'publication_date': publication_date,
                        'title': title,
                        'h1': h1,
                        'lead_html': lead_html,
                        'lead_markdown': lead_markdown,
                        'content_html': content_html,
                        'content_markdown': content_markdown,
                    }

                    if content_markdown != "Контент не найден":                       
                        articles_data.append(article_data)
                        parsed_titles.add(title)
                        article_counter += 1

                except Exception as e:
                    print(f"Ошибка при обработке элемента: {e}")
                finally:
                    driver.close()  # Закрываем вкладку с текущей статьей
                    driver.switch_to.window(driver.window_handles[0])  # Переключаемся обратно на основную вкладку

            # Проверяем наличие пагинации
            try:
                paginator = driver.find_element(By.CLASS_NAME, 'page-nav')
                next_page_button = paginator.find_element(By.XPATH, './/button[contains(@class, "button") and contains(text(), "Вперед")]')
                driver.execute_script("arguments[0].click();", next_page_button)
                WebDriverWait(driver, 10).until(EC.staleness_of(article_elements[0]))  # Ожидаем загрузки следующей страницы
            except NoSuchElementException:
                print("Пагинация не найдена. Парсинг завершен.")
                break  # Если пагинация не найдена, выходим из цикла

        final_article_count = len(articles_data)
        print(f"Успешно спарсено и сохранено статей: {final_article_count}")

    except InvalidSessionIdException as e:
        print(f"Ошибка сессии: {e}")
    except WebDriverException as e:
        print(f"Ошибка при парсинге страницы: {e}")

    return articles_data
                                    
                                             
                                             
def save_to_json(data, filename):
    """Сохранение данных в JSON-файл"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []
    except FileNotFoundError:
        existing_data = []

    existing_data.extend(data)

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)

    print(f"Данные сохранены в файл: {filename}")

def main():
    try:
        url_file = 'urls.txt'
        json_file = 'prosto.json'
        max_articles = 1 # Установите None для парсинга всех статей или задайте максимальное количество статей

        if not os.path.exists(url_file):
            print(f"Файл {url_file} не найден.")
            return

        with open(url_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]

        for url in urls:
            articles_data = parse_article(url, driver, max_articles)
            if articles_data:
                save_to_json(articles_data, json_file)

        # Валидировать JSON-файл
        try:
            df = pd.read_json(json_file)
            print("JSON-файл сформирован корректно.")
        except ValueError as e:
            print(f"Ошибка при валидации JSON-файла: {e}")

    except Exception as ex:
        print(ex)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
