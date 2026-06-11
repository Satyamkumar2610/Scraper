import os
import json
import logging
import hashlib
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from tenacity import retry, wait_exponential, stop_after_attempt

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/india_state_story.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("india_state_story_scraper")

BASE_URL = "https://www.indiastatestory.in/datadownloads"
DATA_DIR = os.path.join("data", "raw", "india_state_story")
METADATA_FILE = os.path.join(DATA_DIR, "metadata.json")


class IndiaStateStoryScraper:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.session = requests.Session()
        # Add basic headers to avoid 403s
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        })
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        if os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
        return {}

    def _save_metadata(self):
        with open(METADATA_FILE, "w") as f:
            json.dump(self.metadata, f, indent=4)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_page(self, url: str) -> str:
        logger.info(f"Fetching page: {url}")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return response.text

    def discover_files(self) -> list[str]:
        """Discover all relevant downloadable files."""
        html = self.fetch_page(BASE_URL)
        soup = BeautifulSoup(html, "html.parser")
        file_urls = []
        
        # Look for all links that could be downloads (pdf, csv, xls, xlsx, zip, or google sheets)
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if any(href.lower().endswith(ext) for ext in [".pdf", ".csv", ".xls", ".xlsx", ".zip"]):
                full_url = urljoin(BASE_URL, href)
                file_urls.append(full_url)
            elif "docs.google.com/spreadsheets/d/" in href:
                # Extract file ID and convert to CSV export link
                # Format: https://docs.google.com/spreadsheets/d/FILE_ID/edit...
                try:
                    file_id = href.split("/d/")[1].split("/")[0]
                    export_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=csv"
                    file_urls.append(export_url)
                except Exception as e:
                    logger.warning(f"Failed to parse Google Sheets URL {href}: {e}")
                
        # Deduplicate
        file_urls = list(set(file_urls))
        logger.info(f"Discovered {len(file_urls)} downloadable files.")
        return file_urls

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def download_file(self, url: str):
        """Download a file with resumable support."""
        if "docs.google.com" in url and "export?format=csv" in url:
            file_id = url.split("/d/")[1].split("/")[0]
            filename = f"{file_id}.csv"
        else:
            filename = url.split("/")[-1]
            # In case there are URL parameters
            filename = filename.split("?")[0]
            if not filename:
                filename = f"download_{hashlib.md5(url.encode()).hexdigest()[:8]}"
            
        filepath = os.path.join(DATA_DIR, filename)

        # Resumable support: Check HEAD response
        try:
            head_resp = self.session.head(url, timeout=10)
            head_resp.raise_for_status()
            remote_size = int(head_resp.headers.get("Content-Length", 0))
        except Exception as e:
            logger.warning(f"Could not fetch headers for {url}: {e}")
            remote_size = 0

        if url in self.metadata and os.path.exists(filepath):
            local_size = os.path.getsize(filepath)
            if remote_size > 0 and local_size == remote_size:
                logger.info(f"Skipping {filename}: already downloaded.")
                return filepath
            elif self.metadata[url].get("file_size") == local_size:
                logger.info(f"Skipping {filename}: already downloaded (metadata matched).")
                return filepath

        logger.info(f"Downloading {filename} from {url}...")
        
        # Stream download
        with self.session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        # Compute checksum
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        checksum = sha256_hash.hexdigest()
        
        file_size = os.path.getsize(filepath)

        self.metadata[url] = {
            "filename": filename,
            "source_url": url,
            "download_date": datetime.utcnow().isoformat(),
            "checksum": checksum,
            "file_size": file_size,
            "last_modified": head_resp.headers.get("Last-Modified") if remote_size > 0 else None
        }
        self._save_metadata()
        logger.info(f"Downloaded {filename} successfully.")
        return filepath

    def run(self):
        logger.info("Starting India State Story Scraper")
        try:
            urls = self.discover_files()
            for url in urls:
                try:
                    self.download_file(url)
                except Exception as e:
                    logger.error(f"Failed to download {url}: {e}")
            logger.info("Scraping completed.")
        except Exception as e:
            logger.error(f"Scraping failed: {e}")

if __name__ == "__main__":
    scraper = IndiaStateStoryScraper()
    scraper.run()
