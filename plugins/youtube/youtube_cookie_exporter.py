#!/usr/bin/env python3
import os, time, json, argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("--user-data-dir=/tmp/yt-session")  # persist login session

# Load and check if cookies are expired
def cookies_still_valid(path):
    if not os.path.exists(path):
        return False
    with open(path, "r") as f:
        for line in f:
            if line.strip().startswith("#") or not line.strip():
                continue
            try:
                parts = line.strip().split("\t")
                if len(parts) < 7:
                    continue
                expiry = int(parts[4])
                if expiry > time.time():
                    return True  # At least one cookie is still valid
            except Exception:
                continue
    return False

def login_to_youtube(driver, wait):
    driver.get("https://www.youtube.com/")
    try:
        driver.find_element(By.CSS_SELECTOR, "#avatar-btn")
        print("Already logged in.")
    except:
        print("Please log in manually...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#avatar-btn")))
        print("Login successful.")

def approve_restricted_consent(driver, wait):
    try:
        btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'I understand and wish to proceed')]"))
        )
        btn.click()
        print("Restricted content consent approved.")
    except:
        print("No consent prompt detected.")

def browse_locations(driver):
    urls = [
        "https://www.youtube.com/feed/trending",
        "https://www.youtube.com/feed/subscriptions",
        "https://www.youtube.com/playlist?list=WL"
    ]
    for url in urls:
        driver.get(url)
        time.sleep(5)

def export_cookies_netscape(driver, path):
    cookies = driver.get_cookies()
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        domain = c["domain"]
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path_ = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expiry = str(int(c.get("expiry", time.time() + 3600)))
        name = c["name"]
        value = c["value"]
        lines.append(f"{domain}\t{include_subdomains}\t{path_}\t{secure}\t{expiry}\t{name}\t{value}")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"Cookies exported in Netscape format to {path}")

def main():
    parser = argparse.ArgumentParser(description="YouTube Cookie Exporter (Netscape Format)")
    parser.add_argument("--cookies", type=str, default="youtube_cookies.txt", help="Path to export/import cookies.txt")
    args = parser.parse_args()

    if cookies_still_valid(args.cookies):
        print("Cookies still valid. No need to re-authenticate.")
        return

    print("Cookies missing or expired. Starting browser for login...")

    service = Service("/usr/lib/chromium/chromedriver")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 20)

    try:
        login_to_youtube(driver, wait)
        approve_restricted_consent(driver, wait)
        browse_locations(driver)
        export_cookies_netscape(driver, args.cookies)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
