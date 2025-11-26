from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException

class LoginPage:
    USERNAME = (By.ID, "gwt-uid-4")
    PASSWORD = (By.ID, "gwt-uid-6")
    LOGIN_TITLE = (By.XPATH, "//div[@class='v-button v-widget primary v-button-primary']")

    def __init__(self, driver: WebDriver, wait_seconds: int = 15) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)

    def at_login(self) -> bool:
        try:
            el = self.wait.until(EC.presence_of_element_located(self.LOGIN_TITLE))
            return (el.text or "").strip() in ["Вход в систему", "Кіру", "Log in", "Вход", "Login"]
        except TimeoutException:
            return False

    def login(self, username: str, password: str) -> None:
        user = self.wait.until(EC.element_to_be_clickable(self.USERNAME))
        user.clear()
        user.send_keys(username)
        pwd = self.wait.until(EC.element_to_be_clickable(self.PASSWORD))
        pwd.clear()
        pwd.send_keys(password, Keys.ENTER)
