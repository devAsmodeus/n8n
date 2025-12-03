import asyncio

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec


async def main() -> None:
    cookies = list()
    for _ in range(15):
        if cookie := await get_cookie():
            cookies.append(cookie)
    else:
        await update_file(cookies)


async def update_file(cookies: list[str]) -> None:
    path = r'C:\Users\Administrator\PycharmProjects\Marketplaces\Cookies\Data\OzonData.txt'
    with open(path, mode='wt+', encoding='utf-8') as file:
        file.writelines('\n'.join(cookies))


async def get_cookie() -> str:
    driver = await create_webdriver()
    try:
        driver.get('https://www.ozon.ru')
        driver.implicitly_wait(30)
        required = (By.CSS_SELECTOR, 'div[data-widget="cookieBubble"]')
        element = ec.presence_of_element_located(required)
        WebDriverWait(driver, 30).until(element)
        cookie = {cookie['name']: cookie['value'] for cookie in driver.get_cookies()}
        return '; '.join(f'{key}={value}' for key, value in cookie.items())
    except:
        pass
    finally:
        driver.close()


async def create_webdriver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.binary_location = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_experimental_option("prefs", {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })
    options.add_argument("--incognito")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    return webdriver.Chrome(options=options)


if __name__ == '__main__':
    asyncio.run(main())
