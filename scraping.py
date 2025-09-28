import sys
import os
import time
import tempfile
import json
import shutil
import warnings
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

# Import the endpoint module
from endpoint import initialize_endpoint, process_new_transaction, get_endpoint_stats, shutdown_endpoint

try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WEBDRIVER_MANAGER = True
except Exception:
    HAS_WEBDRIVER_MANAGER = False
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

# 👇 Add solver repo to PYTHONPATH and try to import solver lazily.
import importlib.util

# The solver depends on heavy ML libraries (torch). Avoid importing the solver
# package at module-import time inside the frozen exe unless those libraries are
# actually available on the target system. Check for 'torch' first and only
# attempt to import the solver when it is present.
HAS_SOLVER = False
CaptchaSolver = None
try:
    if importlib.util.find_spec("torch") is not None:
        # Only add the local solver repo to path and import it when torch exists
        sys.path.append("ReCaptchaV2-DeepLearning-Solver")
        # Prefer the package-level accessor which performs a lazy import
        try:
            from solver import get_captcha_solver as _get_solver
            CaptchaSolver = _get_solver()
            HAS_SOLVER = True
        except Exception:
            # Fallback import if accessor not present (older copies)
            from solver import CaptchaSolver as _CaptchaSolver
            CaptchaSolver = _CaptchaSolver
            HAS_SOLVER = True
    else:
        # PyTorch not present — mark solver as unavailable without importing it.
        HAS_SOLVER = False
except Exception:
    # Any import-time error should not crash the module import; keep solver disabled.
    HAS_SOLVER = False


# Helper to attempt runtime import of solver with diagnostics. Returns a class or None.
def load_solver_class_devlog():
    """Attempt to load the CaptchaSolver class and log any import errors to temp log.

    Returns CaptchaSolver class if available and callable, otherwise None.
    """
    try:
        import importlib
        # prefer accessor
        m = importlib.import_module('solver')
        if hasattr(m, 'get_captcha_solver') and callable(getattr(m, 'get_captcha_solver')):
            cls = m.get_captcha_solver()
            if callable(cls):
                return cls
        if hasattr(m, 'CaptchaSolver') and callable(getattr(m, 'CaptchaSolver')):
            return m.CaptchaSolver
        return None
    except Exception:
        try:
            import tempfile, traceback, datetime
            log_path = os.path.join(tempfile.gettempdir(), 'desktop_scraper_error.log')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n--- {datetime.datetime.now().isoformat()} SOLVER IMPORT ERROR ---\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        return None

def load_user_config():
    """Load user configuration from config file"""
    config_file = 'user_config.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('email', ''), config.get('password', ''), config.get('pages', 1)
        except Exception as e:
            print(f"Error loading config: {e}")
    return '', '', 1

def save_user_config(email, password, pages):
    """Save user configuration to config file"""
    config = {
        'email': email,
        'password': password,
        'pages': pages,
        'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    try:
        with open('user_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"Configuration saved to user_config.json")
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

def get_user_input():
    """Get user input for email, password, and pages"""
    print("=" * 50)
    print("Google Pay Scraper Setup with API Integration")
    print("=" * 50)
    
    # Load existing config
    saved_email, saved_password, saved_pages = load_user_config()
    
    if saved_email:
        print(f"Found saved email: {saved_email}")
        use_saved = input("Use saved configuration? (y/n): ").strip().lower()
        if use_saved == 'y':
            return saved_email, saved_password, saved_pages
    
    # Get new input
    email = input("Enter email address: ").strip()
    while not email or '@' not in email:
        print("Please enter a valid email address")
        email = input("Enter email address: ").strip()
    
    password = input("Enter password: ").strip()
    while not password:
        print("Password cannot be empty")
        password = input("Enter password: ").strip()
    
    pages_input = input("Enter number of pages (default: 1): ").strip()
    try:
        pages = int(pages_input) if pages_input else 1
        if pages <= 0:
            pages = 1
    except ValueError:
        pages = 1
    
    # Ask to save
    save_config = input("Save this configuration? (y/n): ").strip().lower()
    if save_config == 'y':
        save_user_config(email, password, pages)
    
    return email, password, pages

def parse_command_line_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Google Pay Scraper with reCAPTCHA solver and API integration')
    parser.add_argument('--email', type=str, help='Email address')
    parser.add_argument('--password', type=str, help='Password')
    parser.add_argument('--pages', type=int, default=1, help='Number of pages to scrape')
    parser.add_argument('--auto-bypass', action='store_true', help='Auto bypass passkey prompts')
    parser.add_argument('--data', type=str, help='JSON data with credentials')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode for user input')
    
    return parser.parse_args()

# Centralized passkey modal handler
def handle_passkey_prompt(driver, timeout=6, wait_after_close=0.6):
    return False

def handle_common_obstacles(driver):
    """Handle common obstacles that might prevent clicking Next button"""
    obstacles_handled = []
    
    try:
        # 1. Handle "Use passkey" prompts
        passkey_buttons = driver.find_elements(By.XPATH, 
            "//button[contains(text(), 'passkey') or contains(text(), 'Passkey') or contains(@aria-label, 'passkey')]")
        if passkey_buttons:
            for btn in passkey_buttons:
                try:
                    cancel_btn = driver.find_element(By.XPATH, 
                        "//button[contains(text(), 'Cancel') or contains(text(), 'Skip') or contains(text(), 'إلغاء')]")
                    driver.execute_script("arguments[0].click();", cancel_btn)
                    obstacles_handled.append("Passkey prompt cancelled")
                    time.sleep(1)
                    break
                except Exception:
                    pass
        
        # 2. Handle "Try another way" links
        try:
            another_way = driver.find_element(By.XPATH, 
                "//a[contains(text(), 'Try another way') or contains(text(), 'جرب طريقة أخرى')] | //button[contains(text(), 'Try another way')]")
            driver.execute_script("arguments[0].click();", another_way)
            obstacles_handled.append("Clicked 'Try another way'")
            time.sleep(2)
        except Exception:
            pass
        
        # 3. Handle phone verification prompts
        try:
            skip_phone = driver.find_element(By.XPATH, 
                "//button[contains(text(), 'Skip') or contains(text(), 'تخطي')] | //a[contains(text(), 'Skip')]")
            driver.execute_script("arguments[0].click();", skip_phone)
            obstacles_handled.append("Skipped phone verification")
            time.sleep(1)
        except Exception:
            pass
        
        # 4. Handle 2FA/Security prompts
        try:
            not_now_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Not now') or contains(text(), 'ليس الآن')] | //a[contains(text(), 'Not now')]")
            for btn in not_now_buttons:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    obstacles_handled.append("Clicked 'Not now' for security prompt")
                    time.sleep(0.5)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        
        # 5. Handle recovery info prompts
        try:
            skip_recovery = driver.find_element(By.XPATH, 
                "//button[contains(text(), 'Skip') or contains(text(), 'تخطي')] | //a[contains(@class, 'skip') or contains(text(), 'Skip')]")
            driver.execute_script("arguments[0].click();", skip_recovery)
            obstacles_handled.append("Skipped recovery info")
            time.sleep(1)
        except Exception:
            pass
            
        # 6. Handle modal dialogs
        try:
            modal_close = driver.find_elements(By.XPATH, 
                "//button[@aria-label='Close' or contains(@class, 'close') or contains(text(), '×')]")
            for btn in modal_close:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    obstacles_handled.append("Closed modal dialog")
                    time.sleep(1)
                    break
                except Exception:
                    continue
        except Exception:
            pass
        
        # 7. Dismiss any overlay/notification
        try:
            dismiss_buttons = driver.find_elements(By.XPATH, 
                "//button[contains(text(), 'Dismiss') or contains(text(), 'رفض')] | //button[@aria-label='Dismiss']")
            for btn in dismiss_buttons:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                    obstacles_handled.append("Dismissed notification")
                    time.sleep(1)
                    break
                except Exception:
                    continue
        except Exception:
            pass
            
    except Exception as e:
        print(f"Error handling obstacles: {e}")
    
    if obstacles_handled:
        print(f"Handled obstacles: {', '.join(obstacles_handled)}")
    
    return len(obstacles_handled) > 0

def click_next(driver):
    """Enhanced Next button clicker"""
    print("Starting Next button detection and clicking...")
    
    max_attempts = 5
    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1}/{max_attempts}")
        
        obstacles_handled = handle_common_obstacles(driver)
        if obstacles_handled:
            time.sleep(2)
        
        next_selectors = [
            "//button[@id='identifierNext']",
            "//button[@id='passwordNext']", 
            "//div[@id='identifierNext']",
            "//div[@id='passwordNext']",
            "//button[.//span[text()='Next']]",
            "//button[contains(text(), 'Next')]",
            "//input[@value='Next']",
            "//button[.//span[text()='التالي']]",
            "//button[contains(text(), 'التالي')]",
            "//input[@value='التالي']",
            "//button[.//span[contains(text(),'Next')]]",
            "//button[@data-continue='true']",
            "//button[contains(@class, 'next')]"
        ]
        
        next_clicked = False
        for selector in next_selectors:
            try:
                next_btn = driver.find_element(By.XPATH, selector)
                if next_btn.is_displayed() and next_btn.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                    time.sleep(0.5)
                    
                    try:
                        ActionChains(driver).move_to_element(next_btn).click().perform()
                        print(f"Clicked Next using ActionChains (selector: {selector})")
                        next_clicked = True
                        break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", next_btn)
                            print(f"Clicked Next using JavaScript (selector: {selector})")
                            next_clicked = True
                            break
                        except Exception:
                            try:
                                next_btn.click()
                                print(f"Clicked Next directly (selector: {selector})")
                                next_clicked = True
                                break
                            except Exception as e:
                                print(f"Failed to click with selector {selector}: {e}")
                                continue
            except Exception:
                continue
        
        if not next_clicked:
            try:
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                for idx, frame in enumerate(frames):
                    try:
                        driver.switch_to.frame(frame)
                        for selector in next_selectors:
                            try:
                                next_btn = driver.find_element(By.XPATH, selector)
                                if next_btn.is_displayed() and next_btn.is_enabled():
                                    driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                                    time.sleep(0.5)
                                    driver.execute_script("arguments[0].click();", next_btn)
                                    print(f"Clicked Next in iframe {idx} (selector: {selector})")
                                    next_clicked = True
                                    break
                            except Exception:
                                continue
                        if next_clicked:
                            break
                    except Exception as e:
                        print(f"Could not switch to iframe {idx}: {e}")
                    finally:
                        driver.switch_to.default_content()
                    if next_clicked:
                        break
            except Exception:
                pass
        
        if next_clicked:
            time.sleep(3)
            return True
        
        print(f"Next button not found in attempt {attempt + 1}")
        time.sleep(2)
    
    print("Could not find Next button after all attempts")
    return False

def wait_for_primary_action_enabled(driver, timeout=30, poll=0.5):
    end = time.time() + timeout
    while time.time() < end:
        val = driver.execute_script(
            "const el = document.querySelector('.JYXaTc'); if(!el) return null; return el.getAttribute('data-is-primary-action-disabled');"
        )
        if val == "false":
            return True
        time.sleep(poll)
    return False

def is_on_transactions_page(driver):
    """Check if currently on transactions page"""
    try:
        cur = driver.current_url or ''
        # Check for various transaction page indicators
        if any(keyword in cur.lower() for keyword in ['transactions', 'pay.google.com', 'activity', 'history']):
            return True
        
        # Check for transaction elements on page
        transaction_elements = driver.find_elements(By.CSS_SELECTOR, 
            "tr[data-row-id], div.transaction-row, li.transaction-item, .transaction, [data-testid*='transaction']")
        if transaction_elements:
            return True
            
        # Check for activity/history page elements
        activity_elements = driver.find_elements(By.XPATH, 
            "//h1[contains(text(), 'Activity')] | //h1[contains(text(), 'Transactions')] | //h1[contains(text(), 'History')]")
        if activity_elements:
            return True
            
    except Exception:
        pass
    return False

def navigate_to_transactions_page(driver):
    """Navigate to transactions page after successful login"""
    print("Navigating to transactions page...")
    
    # List of possible transaction page URLs to try
    transaction_urls = [
        "https://pay.google.com/gp/w/u/0/home/activity",
        "https://pay.google.com/g4b/u/0/transactions",
        "https://pay.google.com/gp/w/u/0/home/transactions",
        "https://pay.google.com/payments/u/0/home/activity",
        "https://payments.google.com/payments/u/0/home/activity"
    ]
    
    for url in transaction_urls:
        try:
            print(f"Trying URL: {url}")
            driver.get(url)
            time.sleep(3)
            
            if is_on_transactions_page(driver):
                print(f"Successfully reached transactions page: {url}")
                return True
                
        except Exception as e:
            print(f"Failed to load {url}: {e}")
            continue
    
    # If direct URLs fail, try to find activity/transaction links on current page
    print("Looking for transaction/activity links on current page...")
    try:
        # Look for various activity/transaction links
        activity_links = driver.find_elements(By.XPATH, 
            "//a[contains(@href, 'activity')] | //a[contains(@href, 'transactions')] | //a[contains(@href, 'history')] | " +
            "//a[contains(text(), 'Activity')] | //a[contains(text(), 'Transactions')] | //a[contains(text(), 'History')] | " +
            "//button[contains(text(), 'Activity')] | //button[contains(text(), 'Transactions')]")
        
        for link in activity_links:
            try:
                if link.is_displayed():
                    driver.execute_script("arguments[0].click();", link)
                    print(f"Clicked activity/transaction link")
                    time.sleep(3)
                    
                    if is_on_transactions_page(driver):
                        print("Successfully reached transactions page via link")
                        return True
                    break
            except Exception:
                continue
                
    except Exception as e:
        print(f"Error finding activity links: {e}")
    
    print("Could not navigate to transactions page")
    return False

def auto_login_if_needed(driver, email, password):
    """Automatically handle login if redirected back to login page"""
    current_url = driver.current_url or ''
    
    # Check if we're on a login page
    if any(keyword in current_url.lower() for keyword in ['signin', 'login', 'accounts.google.com']):
        print("Detected redirect to login page. Auto-filling credentials...")
        
        # Handle email input
        try:
            email_input = driver.find_element(By.ID, "identifierId")
            if email_input.is_displayed():
                print("Auto-filling email...")
                email_input.clear()
                for ch in email:
                    email_input.send_keys(ch)
                    time.sleep(0.05)
                
                time.sleep(1)
                click_next(driver)
                time.sleep(3)
        except Exception:
            pass
        
        # Handle password input
        try:
            handle_passkey_prompt(driver)
            handle_common_obstacles(driver)
            
            password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "Passwd"))
            )
            if password_input.is_displayed():
                print("Auto-filling password...")
                password_input.clear()
                password_input.send_keys(password)
                
                time.sleep(1)
                click_next(driver)
                time.sleep(3)
        except Exception:
            pass
        
        return True
    return False

def extract_transaction_data(row_element):
    """Extract transaction data from a row element"""
    try:
        transaction = {}
        
        # Try to extract amount
        amount_selectors = [
            ".amount", "[data-amount]", ".transaction-amount", 
            ".money", ".currency", "[class*='amount']"
        ]
        
        for selector in amount_selectors:
            try:
                amount_elem = row_element.find_element(By.CSS_SELECTOR, selector)
                amount_text = amount_elem.text.strip()
                if amount_text:
                    transaction['amount'] = amount_text
                    break
            except:
                continue
        
        # Try to extract description/remarks
        desc_selectors = [
            ".description", ".transaction-desc", ".memo", 
            "[data-description]", "[class*='desc']", ".details"
        ]
        
        for selector in desc_selectors:
            try:
                desc_elem = row_element.find_element(By.CSS_SELECTOR, selector)
                desc_text = desc_elem.text.strip()
                if desc_text:
                    transaction['description'] = desc_text
                    break
            except:
                continue
        
        # Try to extract date
        date_selectors = [
            ".date", ".transaction-date", "[data-date]", 
            ".timestamp", "[class*='date']", "time"
        ]
        
        for selector in date_selectors:
            try:
                date_elem = row_element.find_element(By.CSS_SELECTOR, selector)
                date_text = date_elem.text.strip()
                if date_text:
                    transaction['date'] = date_text
                    break
            except:
                continue
        
        # Try to extract UTR/reference
        utr_selectors = [
            ".utr", ".reference", "[data-utr]", ".transaction-id",
            "[class*='ref']", "[class*='utr']"
        ]
        
        for selector in utr_selectors:
            try:
                utr_elem = row_element.find_element(By.CSS_SELECTOR, selector)
                utr_text = utr_elem.text.strip()
                if utr_text:
                    transaction['utr'] = utr_text
                    break
            except:
                continue
        
        # Extract account info if available
        account_selectors = [
            ".account", "[data-account]", ".account-number", 
            "[class*='account']"
        ]
        
        for selector in account_selectors:
            try:
                account_elem = row_element.find_element(By.CSS_SELECTOR, selector)
                account_text = account_elem.text.strip()
                if account_text:
                    transaction['account_number'] = account_text
                    break
            except:
                continue
        
        # If no specific account found, use a default
        if 'account_number' not in transaction:
            transaction['account_number'] = 'google_pay_account'
        
        # Add timestamp
        from datetime import datetime
        transaction['scraped_at'] = datetime.now().isoformat()
        
        # Only return if we have at least amount
        if 'amount' in transaction:
            return transaction
        
    except Exception as e:
        print(f"Error extracting transaction data: {e}")
    
    return None

# CONFIG
REFRESH_INTERVAL = 30  # seconds

def restart_driver(chrome_options):
    """Restart Chrome driver with error handling"""
    print("Restarting Chrome driver...")
    try:
        if HAS_WEBDRIVER_MANAGER:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            print("webdriver-manager not installed. Relying on chromedriver in PATH.")
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        print("Chrome driver restarted successfully")
        return driver
    except Exception as e:
        print(f"Failed to restart driver: {e}")
        return None

def run_scraper(email: str, password: str, pages: int = 1, auto_bypass: bool = True):
    driver = None
    chrome_options = None
    
    # Initialize the endpoint system
    endpoint_client = initialize_endpoint()
    
    try:
        print(f"Starting scraper for: {email}")
        print(f"Pages to scrape: {pages}")
        print(f"Auto-bypass enabled: {auto_bypass}")
        print("API Integration: ENABLED")
        
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Proxy setup
        http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
        https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
        if http_proxy:
            chrome_options.add_argument(f'--proxy-server={http_proxy}')
            print(f"Using HTTP proxy: {http_proxy}")
        elif https_proxy:
            chrome_options.add_argument(f'--proxy-server={https_proxy}')
            print(f"Using HTTPS proxy: {https_proxy}")
        
        # Initialize driver
        if HAS_WEBDRIVER_MANAGER:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        else:
            print("webdriver-manager not installed. Relying on chromedriver in PATH.")
            driver = webdriver.Chrome(options=chrome_options)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Navigate to Google sign-in with retries
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print(f"Loading Google signin page (attempt {attempt}/{max_retries})")
                driver.get("https://accounts.google.com/signin/v2/identifier")
                time.sleep(3)
                
                if is_on_transactions_page(driver):
                    print("Already logged in - skipping login flow.")
                    break
                break
            except WebDriverException as e:
                print(f"Failed to load page (attempt {attempt}/{max_retries}): {e}")
                if 'ERR_CONNECTION_TIMED_OUT' in str(e):
                    print(" Hint: network timeout. Check your internet connection.")
                if attempt == max_retries:
                    raise
                time.sleep(2)
        
        # Login process
        try:
            if is_on_transactions_page(driver):
                print("Already on transactions/pay page; skipping email entry.")
            else:
                # Enter email
                print("Looking for email input field...")
                email_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "identifierId"))
                )
                print("Entering email...")
                email_input.clear()
                for ch in email:
                    email_input.send_keys(ch)
                    time.sleep(0.05)
                
                time.sleep(2)
                
                # Click Next after email
                print("Attempting to click Next after email...")
                next_success = click_next(driver)
                if not next_success:
                    print("Could not click Next, trying Enter key...")
                    email_input.send_keys(Keys.RETURN)
                
                time.sleep(4)
                
                # Handle passkey and other prompts
                try:
                    if auto_bypass:
                        handle_passkey_prompt(driver)
                        handle_common_obstacles(driver)
                    else:
                        handle_passkey_prompt(driver)
                except Exception:
                    pass
                
            # Handle captcha OR go directly to password
            for step in range(30):
                current_url = driver.current_url
                print(f"[{step}] Current URL: {current_url}")
                
                if is_on_transactions_page(driver):
                    print("Transactions page detected - proceeding.")
                    break

                if "recaptcha" in current_url:
                    print("Captcha challenge detected.")
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='recaptcha']"))
                        )
                        
                        # Use ReCaptchaV2-DeepLearning-Solver (lazy / optional)
                        print("Attempting to use ReCaptchaV2-DeepLearning-Solver (if available)...")
                        # Load the solver class defensively and log import problems to developer log
                        solver_cls = None
                        if HAS_SOLVER and CaptchaSolver is not None and callable(CaptchaSolver):
                            solver_cls = CaptchaSolver
                        else:
                            solver_cls = load_solver_class_devlog()

                        if not solver_cls:
                            print("Captcha auto-solver is not available on this system. Please solve the captcha manually.")
                        else:
                            # Instantiate and run solver with runtime error handling
                            try:
                                solver = solver_cls(driver)
                                if not hasattr(solver, 'solve_captcha') or not callable(getattr(solver, 'solve_captcha')):
                                    raise RuntimeError('Loaded solver does not have a callable solve_captcha()')
                                solver.solve_captcha()
                                print("Captcha solved using DeepLearning solver.")
                            except Exception:
                                # Write full traceback to temp log for diagnostics and print a friendly message
                                try:
                                    import tempfile, traceback, datetime
                                    log_dir = tempfile.gettempdir()
                                    log_path = os.path.join(log_dir, "desktop_scraper_error.log")
                                    with open(log_path, "a", encoding="utf-8") as f:
                                        f.write(f"\n--- {datetime.datetime.now().isoformat()} SOLVER RUNTIME ERROR ---\n")
                                        traceback.print_exc(file=f)
                                except Exception:
                                    pass
                                print("Error while solving captcha (solver raised an exception). See developer log for details.")
                                try:
                                    driver.save_screenshot("captcha_error.png")
                                except Exception:
                                    pass

                        # Wait for the solution to register
                        print("Waiting for captcha solution to register...")
                        time.sleep(5)
                        
                        # Check if we moved to next page automatically
                        new_url = driver.current_url
                        if new_url != current_url and "recaptcha" not in new_url:
                            print("Page progressed automatically after captcha solve!")
                            continue
                        
                        print("Attempting to click Next after captcha solve...")
                        clicked = click_next(driver)
                        if not clicked:
                            print("All click attempts failed after captcha.")
                            try:
                                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.RETURN)
                                print("Tried pressing Enter key")
                                time.sleep(2)
                            except:
                                pass
                        else:
                            print("Successfully clicked Next after captcha solve!")
                            
                        time.sleep(3)
                        final_url = driver.current_url
                        if final_url != current_url:
                            print(f"URL changed from captcha page: {final_url}")
                            continue
                        else:
                            print("Still on captcha page, continuing...")

                    except Exception as e:
                        print("Error while solving captcha:", e)
                        driver.save_screenshot("captcha_error.png")
                        try:
                            click_next(driver)
                        except:
                            pass
                    
                    time.sleep(2)
                    continue
                
                # Handle password page
                if "challenge/pwd" in current_url or "signin/v2/challenge/pwd" in current_url:
                    print("Password page reached.")
                    break
                
                handle_common_obstacles(driver)
                time.sleep(1)
            
            # Enter password
            try:
                print("Looking for password input field...")
                handle_passkey_prompt(driver)
                
                password_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.NAME, "Passwd"))
                )
                print("Entering password...")
                password_input.clear()
                password_input.send_keys(password)
                
                time.sleep(2)
                
                print("Attempting to click Next after password...")
                next_success = click_next(driver)
                if not next_success:
                    print("Could not click Next, trying Enter key...")
                    password_input.send_keys(Keys.RETURN)
                
                time.sleep(5)
                handle_common_obstacles(driver)
                
            except TimeoutException:
                print("Password input not found - might already be logged in.")
            except Exception as e:
                print(f"Error during password entry: {e}")
        
        except Exception as e:
            print(f"Login process error: {e}")
            handle_passkey_prompt(driver)
        
        # Wait for login to complete and navigate to transactions page
        print("Waiting for login to complete...")
        time.sleep(5)
        
        # Navigate to transactions page after successful login
        if not is_on_transactions_page(driver):
            navigate_to_transactions_page(driver)
        
        # Auto-refresh loop with auto-login capability and crash recovery
        print("Starting auto-refresh loop on Transactions page with API integration...")
        collected_payins = []
        refresh_count = 0
        consecutive_failures = 0
        max_failures = 3
        
        try:
            while True:
                refresh_count += 1
                print(f"\nRefresh #{refresh_count} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    # Check if driver is still alive
                    try:
                        _ = driver.current_url
                    except Exception as e:
                        print(f"Driver connection lost: {e}")
                        raise WebDriverException("Driver connection lost")
                    
                    # Check if we got redirected to login and auto-login if needed
                    if auto_login_if_needed(driver, email, password):
                        print("Auto-login completed. Navigating back to transactions...")
                        time.sleep(3)
                        if not is_on_transactions_page(driver):
                            navigate_to_transactions_page(driver)
                    
                    driver.refresh()
                    
                    # Wait for page to load
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Reset failure counter on successful refresh
                    consecutive_failures = 0
                    
                    # Check if we're still on transactions page
                    if not is_on_transactions_page(driver):
                        print("Not on transactions page. Attempting to navigate...")
                        navigate_to_transactions_page(driver)
                    
                    # Look for transaction elements
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.any_of(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "tr[data-row-id]")),
                                EC.presence_of_element_located((By.CSS_SELECTOR, "div.transaction-row")),
                                EC.presence_of_element_located((By.CSS_SELECTOR, "li.transaction-item")),
                                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid*='transaction']"))
                            )
                        )
                        print(f"Transactions page refreshed successfully")
                    except TimeoutException:
                        print("Transaction elements not found, but continuing...")
                    
                    # Find transaction rows
                    rows = []
                    try:
                        # Try multiple selectors for transaction rows
                        selectors = [
                            "tr[data-row-id]",
                            "div.transaction-row", 
                            "li.transaction-item",
                            "[data-testid*='transaction']",
                            ".transaction",
                            "[class*='transaction']",
                            "tr[role='row']"
                        ]
                        
                        for selector in selectors:
                            rows = driver.find_elements(By.CSS_SELECTOR, selector)
                            if rows:
                                print(f"Found {len(rows)} transaction elements using selector: {selector}")
                                break
                    except Exception as e:
                        print(f"Error finding transaction rows: {e}")
                        rows = []
                    
                    if not rows:
                        try:
                            # Fallback: find all table rows
                            container = driver.find_element(By.TAG_NAME, 'body')
                            rows = container.find_elements(By.TAG_NAME, 'tr')
                            if rows:
                                print(f"Fallback: Found {len(rows)} table rows")
                        except Exception:
                            rows = []
                    
                    # Process transactions with API integration
                    new_transactions = 0
                    for row in rows:
                        try:
                            transaction_data = extract_transaction_data(row)
                            if transaction_data:
                                # Check if we already processed this transaction
                                transaction_key = f"{transaction_data.get('amount', '')}_{transaction_data.get('date', '')}_{transaction_data.get('account_number', '')}"
                                
                                if transaction_key not in [t.get('key') for t in collected_payins]:
                                    transaction_data['key'] = transaction_key
                                    collected_payins.append(transaction_data)
                                    new_transactions += 1
                                    
                                    # Send to API in real-time
                                    process_new_transaction(transaction_data)
                                    print(f"Processed new transaction: {transaction_data.get('amount', 'N/A')}")
                        
                        except Exception as e:
                            print(f"Error processing transaction row: {e}")
                            continue
                    
                    print(f"Found {len(rows)} transaction elements this refresh")
                    if new_transactions > 0:
                        print(f"Added {new_transactions} new transactions")
                    print(f"Total collected: {len(collected_payins)} transactions")
                    
                    # Show API statistics
                    stats = get_endpoint_stats()
                    print(f"API Stats: {stats.get('sent_transactions', 0)} sent, {stats.get('success_rate', 0):.1f}% success rate")
                        
                except (WebDriverException, TimeoutException) as driver_error:
                    consecutive_failures += 1
                    print(f"Driver error (attempt {consecutive_failures}/{max_failures}): {str(driver_error)[:100]}...")
                    
                    if consecutive_failures >= max_failures:
                        print(f"Too many consecutive failures. Restarting browser...")
                        
                        # Close current driver
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        
                        # Restart driver
                        driver = restart_driver(chrome_options)
                        if not driver:
                            print("Failed to restart driver. Exiting...")
                            break
                        
                        # Re-login and navigate to transactions
                        print("Re-authenticating after driver restart...")
                        try:
                            # Navigate to sign-in
                            driver.get("https://accounts.google.com/signin/v2/identifier")
                            time.sleep(3)
                            
                            # Auto-login
                            auto_login_if_needed(driver, email, password)
                            time.sleep(5)
                            
                            # Navigate to transactions
                            if not is_on_transactions_page(driver):
                                navigate_to_transactions_page(driver)
                                
                            consecutive_failures = 0  # Reset counter
                            print("Successfully restarted and re-authenticated")
                            
                        except Exception as restart_error:
                            print(f"Failed to re-authenticate: {restart_error}")
                            break
                    else:
                        print(f"Waiting 10 seconds before retry...")
                        time.sleep(10)
                        continue
                        
                except Exception as general_error:
                    print(f"General error during refresh: {general_error}")
                    consecutive_failures += 1
                    
                    if consecutive_failures >= max_failures:
                        print("Too many consecutive errors. Stopping...")
                        break
                
                # Save snapshot of collected data
                try:
                    snapshot_data = {
                        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                        'refresh_count': refresh_count,
                        'consecutive_failures': consecutive_failures,
                        'total_transactions': len(collected_payins),
                        'transactions': collected_payins,
                        'api_stats': get_endpoint_stats()
                    }
                    with open('payins_snapshot.json', 'w', encoding='utf-8') as f:
                        json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
                    
                    # Also save a backup with timestamp every 10 refreshes
                    if refresh_count % 10 == 0:
                        backup_filename = f"payins_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
                        with open(backup_filename, 'w', encoding='utf-8') as f:
                            json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
                        print(f"Backup saved: {backup_filename}")
                        
                except Exception as e:
                    print(f"Error saving snapshot: {e}")
                
                # Wait before next refresh
                print(f"Waiting {REFRESH_INTERVAL} seconds before next refresh...")
                time.sleep(REFRESH_INTERVAL)
                
        except KeyboardInterrupt:
            print("\nAuto-refresh stopped by user.")
            print(f"Final stats: {len(collected_payins)} total transactions collected")
            
            # Show final API stats
            final_stats = get_endpoint_stats()
            print(f"Final API stats: {final_stats}")
            
            # Save final export
            try:
                export_transactions_for_upload(collected_payins)
            except Exception as e:
                print(f"Error saving final export: {e}")
            
    except Exception as e:
        import traceback
        print("Unhandled exception:")
        traceback.print_exc()
        
        # Try to save whatever data we have
        try:
            if 'collected_payins' in locals() and collected_payins:
                export_transactions_for_upload(collected_payins, 'emergency_payins.json')
                print(f"Emergency save completed: {len(collected_payins)} transactions")
        except Exception:
            pass
            
    finally:
        # Shutdown endpoint system
        shutdown_endpoint()
        
        if driver:
            print("Closing browser...")
            driver.quit()

# Helper to export transactions
def export_transactions_for_upload(payins, out_path='payins.json'):
    """Export collected transactions to JSON file"""
    export_data = {
        'export_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_count': len(payins),
        'transactions': payins,
        'api_stats': get_endpoint_stats()
    }
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(payins)} transaction(s) to {out_path}")

if __name__ == "__main__":
    args = parse_command_line_args()
    
    email = None
    password = None
    pages = 1
    auto_bypass = True
    
    # Handle different input methods
    if args.data:
        # JSON data format
        try:
            data = json.loads(args.data)
            email = data.get('email')
            password = data.get('password')
            pages = int(data.get('pages', 1))
            auto_bypass = data.get('auto_bypass', True)
        except Exception as e:
            print(f"Invalid JSON data: {e}")
            sys.exit(1)
    elif args.email and args.password:
        # Command line arguments
        email = args.email
        password = args.password
        pages = args.pages
        auto_bypass = args.auto_bypass
    elif args.interactive:
        # Interactive mode
        email, password, pages = get_user_input()
        auto_bypass = True
    else:
        # Default to interactive mode if no arguments
        print("No arguments provided. Starting interactive mode...")
        email, password, pages = get_user_input()
        auto_bypass = True
    
    if email and password:
        print(f"\nStarting Enhanced Google Pay Scraper with API Integration")
        print(f"Email: {email}")
        print(f"Password: {'*' * len(password)}")
        print(f"Pages: {pages}")
        print(f"Auto-bypass: {auto_bypass}")
        print(f"Auto-refresh: Every {REFRESH_INTERVAL} seconds")
        print(f"Auto-login: Enabled")
        print(f"API Integration: ENABLED")
        print("-" * 50)
        
        run_scraper(email, password, pages, auto_bypass)
    else:
        print("No valid credentials provided. Exiting...")
        sys.exit(1)
