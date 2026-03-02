import logging
import time
from datetime import datetime, timedelta
from typing import Callable, Optional
import threading

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    InvalidSessionIdException,
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.remote.webdriver import WebDriver

from ..telegram import TelegramClient
from ..pages.login_page import LoginPage
from ..schedule import Schedule

logger = logging.getLogger(__name__)


class LoginFailed(Exception):
    """Raised when WSP shows a global login error dialog."""

class AttendanceService:
    ATTEND_BTN = (By.XPATH, "//div[contains(@class,'v-button') and contains(@class,'primary')]")
    LESSON_LABEL = (By.XPATH, "//div[contains(@class,'v-label-bold') and contains(@class,'v-has-width')]")

    def __init__(
        self,
        telegram: TelegramClient,
        schedule: Schedule,
        *,
        base_url: str,
        create_driver: Callable[[], WebDriver],
        user_login: str,
        user_tag: Optional[str] = None,
        wait_seconds: int = 30,
        driver: Optional[WebDriver] = None,
    ) -> None:
        self.driver: Optional[WebDriver] = driver
        self._wait_seconds = wait_seconds
        self.wait: Optional[WebDriverWait] = WebDriverWait(driver, wait_seconds) if driver else None
        self.login_page: Optional[LoginPage] = LoginPage(driver, wait_seconds) if driver else None

        self.tg = telegram
        self.schedule = schedule
        self._create_driver = create_driver
        self.base_url = base_url

        self.user_login = user_login
        self.user_tag = user_tag

        logger.info(
            "AttendanceService initialized (wait_seconds=%s, tz=%s, user=%s)",
            wait_seconds,
            self.schedule.tz.key,
            self.user_login,
        )

    # ---------- infra ----------

    def _user_prefix(self) -> str:
        if self.user_tag:
            return f"[{self.user_login} / {self.user_tag}]"
        return f"[{self.user_login}]"

    def _notify(self, text: str) -> None:
        message = f"{self._user_prefix()} {text}"
        try:
            self.tg.send_message(message)
        except Exception:
            logger.exception("Failed to send Telegram notification for %s", self.user_login)

    def _rebind_driver(self, driver: WebDriver) -> None:
        self.driver = driver
        self.wait = WebDriverWait(driver, self._wait_seconds)
        self.login_page = LoginPage(driver, self._wait_seconds)

    def _open_driver(self, reason: str, notify: bool = True) -> None:
        logger.info("Opening WebDriver (reason: %s, user=%s)", reason, self.user_login)
        drv = self._create_driver()
        self._rebind_driver(drv)
        drv.get(self.base_url)
        if notify:
            self._notify(f"🔧 Browser opened ({reason})")

    def _shutdown_driver(self, reason: str, notify: bool = True) -> None:
        if not self.driver:
            return
        logger.info("Closing WebDriver (reason: %s, user=%s)", reason, self.user_login)
        try:
            self.driver.quit()
        except Exception:
            logger.exception("Error while quitting WebDriver")
        finally:
            self.driver = None
            self.wait = None
            self.login_page = None
        if notify:
            self._notify(f"🌙 Browser closed ({reason})")

    def _safe_url(self) -> str:
        try:
            return self.driver.current_url if self.driver else "<no-driver>"
        except Exception:
            return "<unavailable>"

    # ---------- domain ----------

    def _find_login_error_message(self) -> Optional[str]:
        """Detect text inside the global error dialog (e.g. 'Неверный логин или пароль.')."""
        if not self.driver:
            return None
        try:
            elems = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div.v-window.global-error.v-window-global-error .v-label.v-widget",
            )
            for el in elems:
                text = (el.text or "").strip()
                if text:
                    return text
        except Exception:
            return None
        return None

    def ensure_logged_in(self, username: str, password: str) -> None:
        """If we're on the login page – perform login and wait for result (success or error)."""
        if not (self.driver and self.wait and self.login_page):
            raise RuntimeError("Driver is not initialized")

        logger.debug("Checking login state at %s (user=%s)", self._safe_url(), self.user_login)
        if not self.login_page.at_login():
            return

        logger.info("Detected login screen → attempting login (user=%s)", self.user_login)
        self.login_page.login(username, password)
        logger.info("Login submitted (user=%s)", self.user_login)

        # Give page a few seconds to either leave login screen or show an error dialog.
        deadline = time.time() + 5
        while time.time() < deadline:
            msg = self._find_login_error_message()
            if msg:
                self._notify(f"Login error: {msg}")
                raise LoginFailed(msg)

            if not self.login_page.at_login():
                # Successfully left login page.
                return

            time.sleep(0.5)

        # After waiting, final check for error dialog.
        msg = self._find_login_error_message()
        if msg:
            self._notify(f"Login error: {msg}")
            raise LoginFailed(msg)

    def try_attend_once(self) -> bool:
        if not (self.driver and self.wait):
            raise RuntimeError("Driver is not initialized")
        logger.debug("Waiting for ATTEND button… (user=%s)", self.user_login)
        # Poll for ATTEND button up to ~5s with simple find/click to avoid stale issues.
        deadline = time.time() + 5
        last_exc: Exception | None = None
        while time.time() < deadline:
            try:
                btn = self.driver.find_element(*self.ATTEND_BTN)
                if btn.is_displayed() and btn.is_enabled():
                    logger.info("Clicking ATTEND at %s (user=%s)", self._safe_url(), self.user_login)
                    btn.click()
                    break
            except (NoSuchElementException, StaleElementReferenceException) as e:
                last_exc = e
            time.sleep(0.1)
        else:
            # Timed out waiting for ATTEND – let caller handle as a soft miss.
            raise TimeoutException(f"ATTEND button not found: {last_exc}")

        logger.debug("Waiting for lesson label… (user=%s)", self.user_login)
        lesson_text = self.wait.until(EC.presence_of_element_located(self.LESSON_LABEL)).text
        lesson = (lesson_text or "").split("\n")[0].strip()

        logger.info("Attended lesson: %s (user=%s)", lesson or "<empty>", self.user_login)
        self._notify(f"Attended\n{lesson}")
        return True

    # ---------- main loop ----------

    def run_loop(
        self,
        username: str,
        password: str,
        poll_secs: int = 10,
        stop_event: Optional[threading.Event] = None,
    ) -> None:

        logger.info("Starting loop (poll=%ss, tz=%s, user=%s)", poll_secs, self.schedule.tz.key, self.user_login)

        def sleep_or_stop(seconds: int) -> bool:
            """Sleep up to `seconds`; return True if we should stop."""
            if stop_event is None:
                time.sleep(seconds)
                return False
            return stop_event.wait(timeout=seconds)

        while stop_event is None or not stop_event.is_set():
            now = datetime.now(self.schedule.tz)
            secs = self.schedule.seconds_until_next_open(now)

            if secs > 0:
                if self.driver:
                    self._shutdown_driver("outside schedule window", notify=False)
                wake = now + timedelta(seconds=secs)
                logger.info(
                    "Outside schedule — sleeping until %s (%ds) (user=%s)",
                    wake.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    secs,
                    self.user_login,
                )
                if sleep_or_stop(secs):
                    break
                continue

            if not self.driver:
                self._open_driver("enter schedule window", notify=False)

            try:
                self.ensure_logged_in(username, password)
                try:
                    self.try_attend_once()
                except TimeoutException:
                    logger.info(
                        "ATTEND not available yet at %s; refreshing and retry in %ss (user=%s)",
                        self._safe_url(),
                        poll_secs,
                        self.user_login,
                    )
                    # Force a simple page refresh so that the schedule/ATTEND state updates.
                    try:
                        if self.driver:
                            self.driver.refresh()
                    except Exception:
                        logger.exception("Failed to refresh page after ATTEND Timeout (user=%s)", self.user_login)
                logger.info("Sleeping %ss (inside window) for %s", poll_secs, self.user_login)
                if sleep_or_stop(poll_secs):
                    break

            except LoginFailed as e:
                logger.error("Login failed for %s: %s – stopping worker", self.user_login, e)
                # Driver will be closed by shutdown() from the caller.
                break

            except (InvalidSessionIdException, WebDriverException) as e:
                logger.exception(
                    "WebDriverException/InvalidSessionId: %s; recreating driver (user=%s)", e, self.user_login
                )
                self._shutdown_driver("webdriver error")
                if sleep_or_stop(3):
                    break
                self._open_driver("recover after webdriver error")

            except Exception:
                logger.exception(
                    "Unexpected error in run_loop; retrying in %ss (user=%s)", poll_secs, self.user_login
                )
                if sleep_or_stop(poll_secs):
                    break

    def shutdown(self) -> None:
        self._shutdown_driver("service shutdown")
