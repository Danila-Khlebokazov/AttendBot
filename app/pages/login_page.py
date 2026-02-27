import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

class LoginPage:
    USERNAME = (By.ID, "gwt-uid-4")
    PASSWORD = (By.ID, "gwt-uid-6")
    LOGIN_TITLE = (By.XPATH, "//div[@class='v-button v-widget primary v-button-primary']")
    # Directly target the GB flag <img>; clicking the image should bubble to the button.
    LANG_GB = (By.CSS_SELECTOR, "img.v-icon[src*='flags/gb.png']")

    def __init__(self, driver: WebDriver, wait_seconds: int = 15) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, wait_seconds)

    def at_login(self) -> bool:
        """We are on the login screen if username & password inputs are present."""
        try:
            has_user = bool(self.driver.find_elements(*self.USERNAME))
            has_pwd = bool(self.driver.find_elements(*self.PASSWORD))
            return has_user and has_pwd
        except Exception:
            return False

    def switch_to_english(self) -> None:
        """Best-effort: click the GB flag image if it is present."""
        try:
            imgs = self.driver.find_elements(*self.LANG_GB)
            if not imgs:
                return
            imgs[0].click()
        except Exception:
            # If flag is not found or click fails, just continue with current language.
            pass

    def login(self, username: str, password: str) -> None:
        # Prefer English UI where possible (affects texts we match later).
        self.switch_to_english()

        # Simple polling loop (up to ~5s) to find and fill username/password.
        deadline = time.time() + 5
        last_exc: Exception | None = None
        while time.time() < deadline:
            try:
                user = self.driver.find_element(*self.USERNAME)
                pwd = self.driver.find_element(*self.PASSWORD)
                user.clear()
                user.send_keys(username)
                pwd.clear()
                pwd.send_keys(password, Keys.ENTER)
                return
            except (NoSuchElementException, StaleElementReferenceException) as e:
                last_exc = e
                time.sleep(0.5)

        raise TimeoutException(f"Failed to locate login fields: {last_exc}")
