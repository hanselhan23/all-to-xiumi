import os

from selenium import webdriver
from selenium.common.exceptions import SessionNotCreatedException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.safari.options import Options as SafariOptions
from selenium.webdriver.safari.service import Service as SafariService

from . import config


SUPPORTED_BROWSERS = {"chrome", "edge", "safari"}
CHROMIUM_BROWSERS = {"chrome", "edge"}


def get_selenium_browser_name() -> str:
    name = os.environ.get("WANYOU_SELENIUM_BROWSER", getattr(config, "SELENIUM_BROWSER", "edge"))
    name = (name or "edge").strip().lower()
    if name not in SUPPORTED_BROWSERS:
        raise ValueError(
            "Unsupported Selenium browser "
            f"{name!r}. Set WANYOU_SELENIUM_BROWSER to 'chrome', 'edge', or 'safari'."
        )
    return name


def browser_supports_profile_dir(browser_name: str) -> bool:
    return browser_name in CHROMIUM_BROWSERS


def make_browser_options(browser_name: str, profile_dir: str, *, headless: bool = False, detach: bool = False):
    if browser_name == "safari":
        options = SafariOptions()
        options.page_load_strategy = getattr(config, "PAGE_LOAD_STRATEGY", "eager")
        return options

    options = ChromeOptions() if browser_name == "chrome" else EdgeOptions()
    options.page_load_strategy = getattr(config, "PAGE_LOAD_STRATEGY", "eager")
    if headless:
        options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging")
    options.add_argument("--silent")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-default-apps")
    if not detach:
        options.add_argument("--remote-debugging-pipe")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-dev-shm-usage")
    if browser_name == "edge":
        options.add_argument("--disable-features=msEdgeSidebarV2,EdgeWalletCheckout,msPdfAadIntegration")
    options.add_argument(f"--user-data-dir={profile_dir}")
    try:
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        if detach:
            options.add_experimental_option("detach", True)
    except Exception:
        pass
    return options


def make_webdriver(browser_name: str, options):
    if browser_name == "chrome":
        service = ChromeService(log_output=os.devnull)
        return webdriver.Chrome(options=options, service=service)
    if browser_name == "safari":
        service = SafariService()
        try:
            return webdriver.Safari(options=options, service=service)
        except SessionNotCreatedException as exc:
            message = str(exc)
            if "Allow remote automation" in message or "remote automation" in message.lower():
                raise RuntimeError(
                    "Safari WebDriver 未启用远程自动化。请先运行 `safaridriver --enable`，"
                    "并在 Safari 设置的开发者/Developer 选项中勾选 Allow Remote Automation，"
                    "然后重新运行。"
                ) from exc
            raise
    service = EdgeService(log_output=os.devnull)
    return webdriver.Edge(options=options, service=service)
