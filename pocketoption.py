from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from dotenv import load_dotenv
from os import getenv
import sys
from urllib.parse import quote
from time import sleep, time
from datetime import datetime
from debug import log
from utils import get_time

linux = sys.platform == 'linux'

if linux:
    from pyvirtualdisplay import Display

load_dotenv()

TIMEOUT = 30
ERROR_LIMIT = 2


class UseDriver():
    busy = False

    def __init__(self, driver, retries=1, script=None):
        self.driver = driver
        self.retries = retries
        self.script = script

    def __enter__(self):
        while self.busy:
            sleep(0.1)
        self.busy = True
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.busy = False

    def run(self, fn):
        exc = None
        retry = False
        tries = self.retries
        log('Entering retry loop', False)
        while tries >= 0:
            try:
                if retry:
                    self.driver.refresh()
                    WebDriverWait(self.driver, TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-call")))
                    if self.script:
                        self.driver.execute_script(self.script)
                log(f'Returnig from function {fn.__name__}', False)
                return fn(self.driver)
            except Exception as e:
                log(f'Driver error: {repr(e)} - {e}', False)
                exc = e
                tries -= 1
                retry = True
        now = datetime.now().time().strftime('%H-%M-%S')
        log(f'Saving screenshot {now}...', False)
        self.driver.save_screenshot(f'{fn.__name__}-{now}.png')
        log(f'Current cookies: {self.driver.get_cookies()}', False)
        raise WebDriverException(msg=f'{repr(exc)} - {exc}')

    def quit(self):
        log('Quitting driver...')
        self.driver.quit()


class PocketOption():
    orders = []
    url = 'https://pocketoption.com/pt/cabinet/demo-quick-high-low/'
    driver = None
    demo = True
    display = None
    check_errors = 0

    # script for automatically adding a unique class
    # to every new order created in the deals list
    script = '''
        new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                if (mutation.addedNodes.length) {
                    mutation.addedNodes.forEach(node => {
                        if (node.classList.contains('deals-list__item')) {
                            let pair = node.querySelector('.item-row:first-of-type div > a')
                            let amount = node.querySelector('.item-row:last-of-type div:first-of-type')
                            let endTime = node.querySelector('.item-row:first-of-type div:last-of-type')
            
                            let cls = `o${endTime.textContent.replace(":", "-")}_${pair.textContent.replace("/", "").replace(" ", "-")}_${amount.textContent.replace("$", "").replace(".", "-")}`
                            node.classList.add(cls)
                        }
                    })
                }
            })
        }).observe(document.querySelector('.deals-list'), { childList: true});
    '''

    def __init__(self, ssid, demo=True):
        self.ssid = ssid
        self.demo = demo
        if not self.demo:
            self.url = self.url.replace('demo-', '')
        self.driver = UseDriver(self.create_driver(), script=self.script)

    def create_driver(self):
        cookies = [
            {
                "name": "lang",
                "value": "pt"
            },
            {
                "name": "autologin",
                "value": "a%3A2%3A%7Bs%3A6%3A%22key_id%22%3Bs%3A16%3A%227433d2e621d54a32%22%3Bs%3A7%3A%22user_id%22%3Bs%3A8%3A%2253182629%22%3B%7D"
            },
            {
                "name": "no-login-captcha",
                "value": "1"
            },
            {
                "name": "_yacd_id_53182629",
                "value": "a3e97b8880589ca5294a2b0751b6a039"
            },
            {
                "name": "zoom-width",
                "value": "[[1%2C2%2C0.1666667]]"
            }
        ]

        cookies.append(
            {'name': 'ci_session', 'value': quote(self.ssid, safe='')})

        options = webdriver.ChromeOptions()

        if linux:
            self.display = Display(size=(1400, 800), visible=0)
            self.display.start()
            # comment this like with if the binary is globally available
            options.binary_location = "./ChromePortableGCPM/data/chrome"
            options.add_argument('--single-process')
        else:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')

        options.add_argument('--no-proxy-server')
        options.add_argument("window-size=1400,800")
        options.add_argument("--disable-crash-reporter")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-in-process-stack-traces")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")

        driver = webdriver.Chrome(
            options=options, service=Service(log_path='NUL'))
        driver.get('https://pocketoption.com/404')

        for cookie in cookies:
            driver.add_cookie(cookie)

        driver.get(self.url)

        try:
            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".btn-call")))
        except TimeoutException:
            log('Page failed to load')

        driver.execute_script(self.script)

        return driver

    def select_pair(self, pair, driver):
        try:
            pair_selector = driver.find_element(
                By.CSS_SELECTOR, '.pair-number-wrap')

            pair_selector.click()
            pair_search = driver.find_element(
                By.CSS_SELECTOR, '.search__field')

            parsed_pair = pair[:3] + '/' + \
                pair[3:6] + pair[6:].replace('-', ' ')

            pair_search.send_keys(pair.replace('-OTC', ''))

            available_pairs = driver.find_elements(
                By.CSS_SELECTOR, '.alist__item:not(.alist__item--no-active) .alist__label')
            selected = False
            for pair in available_pairs:
                if pair.text == parsed_pair:
                    pair.click()
                    selected = True

            webdriver.ActionChains(driver).send_keys(
                Keys.ESCAPE).perform()
            if not selected:
                raise NoSuchElementException(msg='Pair not found')
        except WebDriverException as e:
            log('Select pair error:', False)
            raise e

    def select_timeframe(self, timeframe, driver):
        try:
            try:
                # switch expiration selector mode if necessary
                flag = driver.find_element(
                    By.CSS_SELECTOR, '.block--expiration-inputs .fa-flag-checkered')
                flag.click()
            except NoSuchElementException:
                pass

            driver.find_element(
                By.CSS_SELECTOR, '.block--expiration-inputs .control').click()
            timeframes = driver.find_elements(
                By.CSS_SELECTOR, '.dops__timeframes-item')
            for tf in timeframes:
                if tf.text == f'M{timeframe}':
                    tf.click()
        except WebDriverException as e:
            log('Select timeframe error:', False)
            raise e

    def get_balance(self):
        try:
            with self.driver as wrapper:
                def b(driver): return driver.find_element(
                    By.CSS_SELECTOR, f'.js-balance-{"demo" if self.demo else "real"}')
                balance = wrapper.run(b)
                return float(balance.text)
        except (WebDriverException, AttributeError) as e:
            log(f'Balance Error: {e}', False)
            return None

    def buy(self, amount, pair, action, timeframe):
        try:
            with self.driver as wrapper:
                def buy_pair(driver):
                    amount_field = driver.find_element(
                        By.CSS_SELECTOR, '.block--bet-amount .value input')
                    amount_field.send_keys(Keys.CONTROL, 'a', Keys.BACKSPACE)
                    amount_field.send_keys(amount)

                    self.select_pair(pair, driver)
                    self.select_timeframe(timeframe, driver)

                    driver.find_element(
                        By.CSS_SELECTOR, f'.btn-{action}').click()

                wrapper.run(buy_pair)

            id = len(self.orders)
            self.orders.append({'amount': amount, 'active': pair,
                               'direction': action, 'time': time(),  'timeframe': timeframe})
            return True, id
        except WebDriverException as e:
            log(f'Buy Error: {e}', False)
            return False, None

    def check_binary_order(self, id):
        try:
            log(f'Check for order id {id}', False)
            order = self.orders[id]

            if time() - order['time'] < order['timeframe'] * 60:
                # waits for order to finish (plus 1 second of error margin)
                sleep(order['timeframe'] * 60 - (time() - order['time']) + 1)

            with self.driver as wrapper:
                def check(driver: webdriver.Chrome):
                    # switch closed deals tab
                    driver.find_elements(
                        By.CSS_SELECTOR, '.deals a.flex-centered')[1].click()

                    order_class = f'.o{get_time(order["time"] + order["timeframe"] * 60).replace(":", "-")}_{order["active"]}_{"{:.2f}".format(order["amount"]).replace(".", "-")}'

                    log(
                        f'Checking deals for {order_class}', False)

                    WebDriverWait(driver, TIMEOUT).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, order_class)))

                    deal = driver.find_element(
                        By.CSS_SELECTOR, order_class)

                    # look for the profit from the order
                    profit_elem = deal.find_element(
                        By.CSS_SELECTOR, '.centered')

                    pair = deal.find_element(
                        By.CSS_SELECTOR, '.item-row:first-of-type div > a')

                    amount = deal.find_element(
                        By.CSS_SELECTOR, '.item-row:last-of-type div:first-of-type')

                    end_time = deal.find_element(
                        By.CSS_SELECTOR, '.item-row:first-of-type div:last-of-type')

                    order['profit_amount'] = float(
                        profit_elem.text.replace('$', ''))

                    log(f'Result: {end_time.text} | {pair.text} | In = {amount.text} | Out = {profit_elem.text}', False)

                wrapper.run(check)

            if 'profit_amount' not in order:
                self.check_errors += 1
                return None

            if order['profit_amount'] > 0:
                order['result'] = 'win'
            else:
                order['result'] = 'loss'

            self.check_errors = 0
            return order
        except WebDriverException as e:
            log(f'Check order error: {e}', False)
            self.check_errors += 1
            if self.check_errors == ERROR_LIMIT:
                log('Restarting driver...', False)
                self.restart(update_token=True)
            return None

    def quit(self):
        self.driver.quit()
        if self.display:
            self.display.stop()

    def restart(self, update_token=False):
        self.driver = UseDriver(self.create_driver())


# if __name__ == '__main__':
#     POCKET_SSID = getenv('POCKETOPTION_SESSION')

#     api = PocketOption(POCKET_SSID)

#     print(api.get_balance())

#     def buy1():
#         check, id = api.buy(1, 'EURUSD', 'put', 1)
#         print(api.check_binary_order(id))

#     def buy2():
#         check, id = api.buy(1, 'EURCAD', 'call', 1)
#         print(api.check_binary_order(id))

#     def buy3():
#         check, id = api.buy(1, 'GBPJPY', 'call', 1)
#         if check:
#             print(api.check_binary_order(id))

#     buy1()
#     buy2()
#     buy3()

#     sleep(5)

#     api.quit()
