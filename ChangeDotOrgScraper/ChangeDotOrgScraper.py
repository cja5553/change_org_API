import requests
from bs4 import BeautifulSoup
import json
from tqdm import tqdm
import re
import pandas as pd
import time
import requests
from bs4 import BeautifulSoup
import json
import re


def normalize_url(url):
    """
    Normalizes the search URL to ensure proper format for pagination.

    Parameters:
    - url (str): Original search URL

    Returns:
    - str: Base URL ready for pagination
    """
    # Remove any existing page parameter
    url = re.sub(r'[&?]page=\d+', '', url)

    # Ensure offset parameter exists
    if 'offset=' not in url:
        if '?' in url:
            url = url + '&offset=0'
        else:
            url = url + '?offset=0'
    else:
        # Reset offset to 0
        url = re.sub(r'offset=\d+', 'offset=0', url)

    return url


def build_page_url(base_url, page_num):
    """
    Builds the URL for a specific page number.

    Parameters:
    - base_url (str): Base search URL with offset=0
    - page_num (int): Page number (1-indexed)

    Returns:
    - str: URL for the specified page
    """
    # Calculate offset (10 results per page)
    offset = (page_num - 1) * 10

    # Replace offset value
    page_url = re.sub(r'offset=\d+', f'offset={offset}', base_url)

    # Add page parameter
    if '&page=' not in page_url and '?page=' not in page_url:
        page_url = page_url + f'&page={page_num}'
    else:
        page_url = re.sub(r'page=\d+', f'page={page_num}', page_url)

    return page_url


def extract_petition_from_card(card_element):
    """
    Extracts petition data from a petition card element.

    Parameters:
    - card_element: BeautifulSoup element representing a petition card

    Returns:
    - dict: Petition data
    """
    try:
        # Get the petition URL
        href = card_element.get('href', '')
        slug = href.replace('/p/', '') if href else ''

        # Skip if not a petition link
        if not href or '/p/' not in href:
            return None

        # Try to find title - look in parent elements
        title = ''

        # Method 1: Look within the card for text content
        title_candidates = card_element.find_all(['h2', 'h3', 'h4', 'span', 'div'])
        for candidate in title_candidates:
            text = candidate.get_text(strip=True)
            if len(text) > 20 and len(text) < 500:
                title = text
                break

        # Method 2: Get text from link itself
        if not title:
            title = card_element.get_text(strip=True)

        # Method 3: Look at parent container
        if not title or len(title) < 10:
            parent = card_element.find_parent(['div', 'article', 'li'])
            if parent:
                # Find heading elements in parent
                heading = parent.find(['h2', 'h3', 'h4'])
                if heading:
                    title = heading.get_text(strip=True)

        # Skip if no valid title found
        if not title or len(title) < 5:
            return None

        # Look for signature count in parent container
        signatures = 0
        parent = card_element.find_parent(['div', 'article', 'li'])
        if parent:
            card_text = parent.get_text()
            sig_patterns = [
                r'([\d,]+)\s*(?:signatures?|supporters?|signed)',
                r'([\d,]+)\s*have signed',
                r'signed:\s*([\d,]+)'
            ]

            for pattern in sig_patterns:
                match = re.search(pattern, card_text, re.IGNORECASE)
                if match:
                    signatures = int(match.group(1).replace(',', ''))
                    break

        # Look for creator name
        creator = ''
        if parent:
            creator_patterns = [r'by\s+([A-Za-z\s\.]+)', r'started by\s+([A-Za-z\s\.]+)']
            card_text = parent.get_text()
            for pattern in creator_patterns:
                match = re.search(pattern, card_text, re.IGNORECASE)
                if match:
                    creator = match.group(1).strip()[:50]  # Limit length
                    break

        # Check for victory status
        victory = False
        if parent:
            victory = 'victory' in parent.get_text().lower()

        return {
            'Petition title': title[:500],  # Limit title length
            'Description': '',
            'signature count': signatures,
            'creator': creator,
            'date created': '',
            'location created': '',
            'Victory verification status': victory,
            'slug': slug,
            'url': f'https://www.change.org{href}' if href.startswith('/') else href
        }

    except Exception:
        return None


def scrape_with_selenium(url, max_pages=None):
    """
    Scrapes Change.org search results using Selenium with proper pagination.

    Parameters:
    - url (str): Search URL from change.org
    - max_pages (int): Maximum number of pages to scrape (None = all pages)

    Returns:
    - list[dict]: List of petitions
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("Selenium not installed. Install with: pip install selenium webdriver-manager")
        return []

    # Normalize the URL
    base_url = normalize_url(url)
    print(f"Base URL: {base_url}")

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Initialize driver
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error initializing Chrome driver: {e}")
        return []

    all_petitions = []
    seen_slugs = set()  # Track seen petitions to avoid duplicates
    page_num = 1
    consecutive_empty_pages = 0
    max_empty_pages = 3  # Stop after 3 consecutive empty pages

    try:
        # Create progress bar (will update dynamically)
        pbar = tqdm(desc="Scraping pages", unit="page")

        while True:
            # Check max_pages limit
            if max_pages and page_num > max_pages:
                print(f"\nReached max_pages limit ({max_pages})")
                break

            # Build URL for current page
            page_url = build_page_url(base_url, page_num)
            pbar.set_description(f"Scraping page {page_num}")

            # Navigate to page
            driver.get(page_url)

            # Wait for page to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/p/"]'))
                )
                time.sleep(2)  # Additional wait for dynamic content
            except:
                # No petition links found - might be end of results
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= max_empty_pages:
                    print(f"\nNo more results found after page {page_num - max_empty_pages}")
                    break
                page_num += 1
                pbar.update(1)
                continue

            # Parse page content
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # Find all petition links
            petition_links = soup.find_all('a', href=re.compile(r'^/p/[^/]+/?$'))

            # Extract petitions from this page
            page_petitions = []
            for link in petition_links:
                petition_data = extract_petition_from_card(link)
                if petition_data:
                    slug = petition_data.get('slug', '')
                    # Only add if not seen before
                    if slug and slug not in seen_slugs:
                        seen_slugs.add(slug)
                        page_petitions.append(petition_data)

            # Check if we got any new petitions
            if not page_petitions:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= max_empty_pages:
                    print(f"\nNo new results found after page {page_num - max_empty_pages + 1}")
                    break
            else:
                consecutive_empty_pages = 0
                all_petitions.extend(page_petitions)
                pbar.set_postfix({'total_petitions': len(all_petitions)})

            # Check for "no results" message
            page_text = soup.get_text().lower()
            if 'no results' in page_text or 'no petitions found' in page_text:
                print(f"\n'No results' message found on page {page_num}")
                break

            # Move to next page
            page_num += 1
            pbar.update(1)

            # Small delay to be respectful to the server
            time.sleep(1)

        pbar.close()

    except KeyboardInterrupt:
        print("\nScraping interrupted by user")

    except Exception as e:
        print(f"\nError during scraping: {e}")

    finally:
        driver.quit()

    print(f"\n{'='*50}")
    print(f"Total pages taken: {page_num - 1}")
    print(f"Total unique petitions found: {len(all_petitions)}")
    print(f"{'='*50}")
    print("Proceeding to extract info from each petition")

    return all_petitions


def get_petitions(url, max_pages=None):
    """
    Main function to scrape Change.org petitions (Selenium only).

    Parameters:
    - url (str): Change.org search URL
    - max_pages (int): Maximum pages to scrape (None = all pages)

    Returns:
    - list[dict]: List of petitions
    """
    # print("Scraping method: selenium")
    print(f"Max pages: {'unlimited' if max_pages is None else max_pages}")
    print()
    return scrape_with_selenium(url, max_pages=max_pages)




def scrape_change_org(url: str) -> dict:
    soup = BeautifulSoup(requests.get(url).text, "lxml")
    XXX = soup.prettify()

    # brief description (meta description)
    tag = soup.find("meta", attrs={"name": "description"})
    brief_description = tag.get("content") if tag else None

    # 1) signatureCount dict (FIRST instance)
    needle = 'signatureCount":'
    i = XXX.find(needle)
    signatureCount = None
    if i != -1:
        start = XXX.find("{", i)
        end = XXX.find("}", start) + 1
        signatureCount = json.loads(XXX[start:end])

    # 2) petition owner displayName
    m = re.search(r'"petition":\{"id":"\d+","user":\{"id":"\d+","displayName":"([^"]+)"', XXX)
    author_display_name = m.group(1) if m else None

    # 3) Petition created on DATE
    m = re.search(r"Petition created on\s*([^<]+)", XXX)
    created_on = m.group(1).strip() if m else None

    # 4) ALL decision maker displayNames
    decision_makers = re.findall(
        r'"decisionMakers":\[\{"id":"\d+","slug":"[^"]+","displayName":"([^"]+)"',
        XXX
    )
    decision_makers = list(dict.fromkeys(decision_makers))  # dedupe keep order

    return {
        "url": url,
        "brief_description": brief_description,
        "signatureCount": signatureCount,
        "author_display_name": author_display_name,
        "created_on": created_on,
        "decision_makers": decision_makers,
    }




def get_all_info(list_of_petitions, sleep_sec=0.5):
    list_of_info = []

    for p in tqdm(list_of_petitions, desc="Fetching petition pages"):
        pet_url = p.get("url")
        if not pet_url:
            continue

        try:
            info = scrape_change_org(pet_url)   # <-- your function
            list_of_info.append(info)
            time.sleep(sleep_sec)  # be polite / avoid getting blocked
            
        except Exception as e:
            list_of_info.append({
                "url": pet_url,
                "signatureCount": None,
                "author_display_name": None,
                "created_on": None,
                "error": str(e)
            })

    return list_of_info




def scrape_petitions(url,max_pages=None):
    if max_pages==None:
        print("No max pages specified, defaulting to 10 pages")
        max_pages=10
    else:
        pass
    list_of_petitions = get_petitions(url, max_pages=max_pages)
    list_of_info = get_all_info(list_of_petitions)
    
    # build table
    rows = []
    for p, info in zip(list_of_petitions, list_of_info):
        rows.append({
            "petition_title": p.get("Petition title"),
            "url": p.get("url"),
            **info
        })
    
    df = pd.DataFrame(rows)
    
    # optional: drop duplicate url column coming from info dict
    df = df.drop(columns=["url"], errors="ignore").assign(url=[p.get("url") for p in list_of_petitions])
    
    return(df)


