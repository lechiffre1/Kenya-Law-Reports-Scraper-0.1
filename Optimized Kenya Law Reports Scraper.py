#!/usr/bin/env python3
"""
Kenya Law Reports Optimized Scraper

A focused scraper for the new.kenyalaw.org/judgements website with
specific optimizations for that site's structure and pagination system.
"""

import os
import re
import time
import json
import random
import logging
import argparse
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import csv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('klr_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('klr_scraper')

# Constants
BASE_URL = 'https://new.kenyalaw.org/judgments/'
SEARCH_URL = 'https://new.kenyalaw.org/judgments/search'
JUDGMENT_DIR = 'KLR'
METADATA_FILE = os.path.join(JUDGMENT_DIR, 'metadata.csv')
PROGRESS_FILE = os.path.join(JUDGMENT_DIR, 'progress.json')
ERROR_LOG = os.path.join(JUDGMENT_DIR, 'errors.log')

# User agent rotation to avoid detection
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/91.0.4472.80 Mobile/15E148 Safari/604.1',
]

# Rate limiting parameters
MIN_DELAY = 1.0  # Minimum delay between requests in seconds
MAX_DELAY = 3.0  # Maximum delay between requests in seconds
MAX_RETRIES = 5  # Maximum number of retries for failed requests
BACKOFF_FACTOR = 2  # Exponential backoff factor for retries

# Scraping parameters
RESULTS_PER_PAGE = 20  # Number of results per page
MAX_WORKERS = 3  # Number of parallel workers (keep low to avoid server strain)


class KenyaLawReportsScraper:
    def __init__(self, output_dir=JUDGMENT_DIR, resume=True, max_pages=None, start_page=1):
        """Initialize the scraper with the given parameters."""
        self.output_dir = output_dir
        self.resume = resume
        self.max_pages = max_pages
        self.start_page = start_page
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Create directories for different court hierarchies
        self.courts = [
            'supreme_court',
            'court_of_appeal',
            'high_court',
            'employment_and_labour_court',
            'environment_and_land_court',
            'magistrates_courts',
            'specialized_tribunals',
            'other_courts'
        ]
        
        for court in self.courts:
            court_dir = os.path.join(output_dir, court)
            if not os.path.exists(court_dir):
                os.makedirs(court_dir)
            
        # Initialize session with cookies and headers
        self.session = requests.Session()
        
        # Load progress if resuming
        self.progress = self._load_progress() if resume else {
            'scraped_judgments': set(),
            'last_page': 0,
            'errors': []
        }
        
        # Initialize metadata CSV file if it doesn't exist
        if not os.path.exists(METADATA_FILE):
            with open(METADATA_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'id', 'case_number', 'title', 'court', 'date', 
                    'judges', 'parties', 'filename', 'url', 'scraped_at'
                ])
        
        # Initialize error log if it doesn't exist
        if not os.path.exists(ERROR_LOG):
            with open(ERROR_LOG, 'w', encoding='utf-8') as f:
                f.write("# Kenya Law Reports Scraper Error Log\n\n")
    
    def _load_progress(self):
        """Load progress from file if it exists."""
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    progress = json.load(f)
                    # Convert scraped_judgments list to set for faster lookups
                    progress['scraped_judgments'] = set(progress['scraped_judgments'])
                    return progress
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Progress file corrupted: {str(e)}. Starting from scratch.")
                return {'scraped_judgments': set(), 'last_page': 0, 'errors': []}
        return {'scraped_judgments': set(), 'last_page': 0, 'errors': []}
    
    def _save_progress(self):
        """Save current progress to file."""
        # Convert set to list for JSON serialization
        progress_copy = self.progress.copy()
        progress_copy['scraped_judgments'] = list(self.progress['scraped_judgments'])
        
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress_copy, f)
    
    def _get_random_user_agent(self):
        """Return a random user agent from the list."""
        return random.choice(USER_AGENTS)
    
    def _log_error(self, message, url=None):
        """Log an error to the error log file."""
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"## {timestamp}\n")
            f.write(f"{message}\n")
            if url:
                f.write(f"URL: {url}\n")
            f.write("\n")
        
        # Also add to progress errors
        self.progress['errors'].append({
            'timestamp': timestamp,
            'message': message,
            'url': url
        })
    
    def _make_request(self, url, method='get', data=None, params=None):
        """Make a request with exponential backoff retry logic."""
        headers = {
            'User-Agent': self._get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        retries = 0
        
        while retries <= MAX_RETRIES:
            try:
                if method.lower() == 'get':
                    response = self.session.get(url, headers=headers, params=params, timeout=30)
                else:  # POST
                    response = self.session.post(url, headers=headers, data=data, timeout=30)
                
                # Check if we're being rate limited or got an error
                if response.status_code == 429:
                    wait_time = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited. Waiting for {wait_time} seconds.")
                    time.sleep(wait_time)
                    retries += 1
                    continue
                
                if response.status_code >= 400:
                    logger.warning(f"HTTP error {response.status_code} for {url}. Retrying...")
                    time.sleep(MIN_DELAY * (BACKOFF_FACTOR ** retries))
                    retries += 1
                    continue
                
                return response
                
            except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
                logger.warning(f"Request error for {url}: {str(e)}. Retrying...")
                time.sleep(MIN_DELAY * (BACKOFF_FACTOR ** retries))
                retries += 1
        
        logger.error(f"Failed to fetch {url} after {MAX_RETRIES} retries.")
        self._log_error(f"Failed to fetch after {MAX_RETRIES} retries", url)
        return None
    
    def _determine_court_directory(self, court_name):
        """Determine the appropriate directory for a judgment based on court name."""
        court_name = court_name.lower() if court_name else ""
        
        if "supreme court" in court_name:
            return os.path.join(self.output_dir, "supreme_court")
        elif "court of appeal" in court_name:
            return os.path.join(self.output_dir, "court_of_appeal")
        elif "high court" in court_name:
            return os.path.join(self.output_dir, "high_court")
        elif "employment" in court_name or "labour" in court_name:
            return os.path.join(self.output_dir, "employment_and_labour_court")
        elif "environment" in court_name or "land" in court_name:
            return os.path.join(self.output_dir, "environment_and_land_court")
        elif "magistrate" in court_name:
            return os.path.join(self.output_dir, "magistrates_courts")
        elif "tribunal" in court_name:
            return os.path.join(self.output_dir, "specialized_tribunals")
        else:
            return os.path.join(self.output_dir, "other_courts")
    
    def get_total_pages(self):
        """Get the total number of pages of results."""
        # Start with a search to get the total results
        response = self._make_request(SEARCH_URL)
        if not response:
            logger.error("Failed to get total pages. Exiting.")
            return 0
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for pagination information
        try:
            # Check for search result count
            result_text = soup.select_one('.search-result-count')
            if result_text:
                text = result_text.text.strip()
                # Extract total from text like "275,979 Results"
                total_results = int(re.sub(r'[^\d]', '', text))
                return (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
            
            # Alternative: check last page button
            pagination = soup.select('.pagination a')
            if pagination:
                last_page = 0
                for link in pagination:
                    if link.get('href'):
                        page_match = re.search(r'page=(\d+)', link.get('href'))
                        if page_match:
                            page = int(page_match.group(1))
                            last_page = max(last_page, page)
                
                if last_page > 0:
                    return last_page
                
        except Exception as e:
            logger.error(f"Error parsing total pages: {str(e)}")
            self._log_error(f"Error parsing total pages: {str(e)}")
        
        # Default fallback - use the known total divided by results per page
        logger.warning("Using default total judgments count (275,979)")
        return (275979 + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    
    def get_judgments_on_page(self, page):
        """Get all judgment links from a specific page."""
        logger.info(f"Scraping judgments on page {page}")
        
        # Construct the search URL with the page parameter
        url = f"{SEARCH_URL}?page={page}"
        response = self._make_request(url)
        
        if not response:
            logger.error(f"Failed to fetch page {page}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        judgments = []
        
        # Find all judgment cards or containers
        judgment_cards = soup.select('.card') or soup.select('.case-result') or soup.select('.search-result-item')
        
        if not judgment_cards:
            # If specific selectors don't work, try more generic ones
            judgment_cards = soup.select('article') or soup.select('.result-item')
        
        for card in judgment_cards:
            try:
                # Extract judgment link
                link_elem = card.select_one('h2 a') or card.select_one('h3 a') or card.select_one('.title a') or card.select_one('a')
                if not link_elem:
                    continue
                    
                link = link_elem.get('href', '')
                if not link:
                    continue
                
                # Ensure the link is absolute
                if not link.startswith('http'):
                    link = urljoin(BASE_URL, link)
                
                # Extract judgment ID from URL
                judgment_id = os.path.basename(urlparse(link).path).split('.')[0]
                if not judgment_id or judgment_id in self.progress['scraped_judgments']:
                    continue
                
                # Extract title
                title = link_elem.text.strip()
                
                # Extract metadata
                metadata = {}
                metadata_items = card.select('.metadata-item') or card.select('.case-meta li') or card.select('.meta')
                
                for item in metadata_items:
                    text = item.text.strip()
                    if ':' in text:
                        key, value = text.split(':', 1)
                        key = key.strip().lower().replace(' ', '_')
                        metadata[key] = value.strip()
                
                # Look for specific metadata we need
                case_number = metadata.get('case_number') or metadata.get('case_no') or metadata.get('number') or ''
                court = metadata.get('court') or metadata.get('court_name') or ''
                date = metadata.get('date') or metadata.get('judgment_date') or ''
                judges = metadata.get('judge') or metadata.get('judges') or metadata.get('coram') or ''
                parties = metadata.get('parties') or title
                
                judgments.append({
                    'id': judgment_id,
                    'link': link,
                    'title': title,
                    'case_number': case_number,
                    'court': court,
                    'date': date,
                    'judges': judges,
                    'parties': parties,
                    'page': page
                })
                
            except Exception as e:
                logger.error(f"Error parsing judgment card: {str(e)}")
                self._log_error(f"Error parsing judgment card: {str(e)}")
        
        logger.info(f"Found {len(judgments)} judgments on page {page}")
        return judgments
    
    def save_judgment(self, judgment_data):
        """Fetch and save an individual judgment and its metadata."""
        link = judgment_data['link']
        judgment_id = judgment_data['id']
        
        # Skip if already scraped
        if judgment_id in self.progress['scraped_judgments']:
            logger.debug(f"Skipping already scraped judgment: {judgment_id}")
            return judgment_data
        
        # Random delay to avoid overloading the server
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        
        # Fetch the judgment page
        response = self._make_request(link)
        if not response:
            logger.error(f"Failed to fetch judgment: {link}")
            judgment_data['status'] = 'failed'
            self._log_error(f"Failed to fetch judgment {judgment_id}", link)
            return judgment_data
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        try:
            # Enhanced metadata extraction from the judgment page
            judgment_metadata = judgment_data.copy()
            
            # Extract more precise metadata if available
            meta_elems = soup.select('.case-metadata .metadata-item') or soup.select('.judgment-metadata span')
            for elem in meta_elems:
                text = elem.text.strip()
                if ':' in text:
                    key, value = text.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    judgment_metadata[key] = value.strip()
            
            # Create sanitized case number for filename
            court_dir = self._determine_court_directory(judgment_metadata.get('court', ''))
            
            # Create appropriate filename
            if judgment_metadata.get('case_number'):
                # Sanitize case number for filename
                case_number = re.sub(r'[\\/*?:"<>|]', '_', judgment_metadata['case_number'])
                case_number = case_number.replace(' ', '_').replace('/', '_').strip('_')
                filename = f"{case_number}_{judgment_id}.html"
            else:
                filename = f"{judgment_id}.html"
            
            # Extract judgment content
            content = None
            
            # Try different possible content selectors
            for selector in ['#judgment-content', '.judgment-content', '.case-content', 'article', '.main-content', '.content-area']:
                content_elem = soup.select_one(selector)
                if content_elem and len(content_elem.text.strip()) > 100:  # Ensure meaningful content
                    content = content_elem
                    break
            
            if not content:
                # If still no content, try getting the main text area
                main_content = soup.find('main') or soup.find('article') or soup.select_one('.content')
                if main_content:
                    content = main_content
            
            if content:
                # Save the judgment HTML
                file_path = os.path.join(court_dir, filename)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(str(content))
                
                # Save metadata to CSV
                with open(METADATA_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        judgment_id,
                        judgment_metadata.get('case_number', ''),
                        judgment_metadata.get('title', ''),
                        judgment_metadata.get('court', ''),
                        judgment_metadata.get('date', ''),
                        judgment_metadata.get('judges', ''),
                        judgment_metadata.get('parties', ''),
                        filename,
                        link,
                        datetime.now().isoformat()
                    ])
                
                # Update progress
                self.progress['scraped_judgments'].add(judgment_id)
                self._save_progress()
                
                logger.info(f"Successfully saved judgment: {filename}")
                judgment_metadata['status'] = 'success'
                judgment_metadata['filename'] = filename
                return judgment_metadata
                
            else:
                logger.warning(f"Could not find judgment content: {link}")
                judgment_data['status'] = 'no_content'
                self._log_error(f"Could not find judgment content for {judgment_id}", link)
                return judgment_data
                
        except Exception as e:
            logger.error(f"Error saving judgment {link}: {str(e)}")
            judgment_data['status'] = 'error'
            judgment_data['error'] = str(e)
            self._log_error(f"Error saving judgment {judgment_id}: {str(e)}", link)
            return judgment_data
    
    def scrape(self):
        """Main scraping function to fetch all judgments."""
        # Get the total number of pages
        total_pages = self.get_total_pages()
        if not total_pages:
            logger.error("Could not determine total pages. Exiting.")
            return
        
        logger.info(f"Found {total_pages} pages of judgments")
        
        # Apply user limits if specified
        if self.max_pages:
            total_pages = min(total_pages, self.max_pages)
            logger.info(f"Limited to {total_pages} pages as requested")
        
        # Set start page based on resume flag
        start_page = max(self.progress['last_page'] + 1, self.start_page) if self.resume else self.start_page
        logger.info(f"Starting from page {start_page}")
        
        # Initialize statistics
        stats = {
            'total_scraped': 0,
            'success': 0,
            'failed': 0,
            'no_content': 0,
            'errors': 0,
            'skipped': 0
        }
        
        # Process each page
        for page in range(start_page, total_pages + 1):
            try:
                logger.info(f"Processing page {page} of {total_pages}")
                judgments = self.get_judgments_on_page(page)
                
                if not judgments:
                    logger.warning(f"No judgments found on page {page}")
                    continue
                
                # Update statistics for judgments found
                stats['total_scraped'] += len(judgments)
                
                # Use ThreadPoolExecutor for parallel processing
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    results = list(tqdm(
                        executor.map(self.save_judgment, judgments),
                        total=len(judgments),
                        desc=f"Page {page}/{total_pages}"
                    ))
                
                # Update statistics based on results
                for result in results:
                    if result.get('status') == 'success':
                        stats['success'] += 1
                    elif result.get('status') == 'failed':
                        stats['failed'] += 1
                    elif result.get('status') == 'no_content':
                        stats['no_content'] += 1
                    elif result.get('status') == 'error':
                        stats['errors'] += 1
                    else:
                        stats['skipped'] += 1
                
                # Update and save progress
                self.progress['last_page'] = page
                self._save_progress()
                
                # Log current statistics
                logger.info(f"Statistics: {stats}")
                
                # Add a delay between pages
                time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                
            except Exception as e:
                logger.error(f"Error processing page {page}: {str(e)}")
                self._log_error(f"Error processing page {page}: {str(e)}")
        
        # Log final statistics
        logger.info(f"Scraping completed. Final statistics: {stats}")
        
        # Create a summary file
        summary_path = os.path.join(self.output_dir, 'summary.json')
        with open(summary_path, 'w', encoding='utf-8') as f:
            summary = {
                'total_pages_scraped': total_pages - start_page + 1,
                'total_judgments_found': stats['total_scraped'],
                'total_judgments_saved': stats['success'],
                'failed': stats['failed'],
                'no_content': stats['no_content'],
                'errors': stats['errors'],
                'skipped': stats['skipped'],
                'completed_at': datetime.now().isoformat()
            }
            json.dump(summary, f, indent=2)
        
        logger.info(f"Scraping summary saved to {summary_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape Kenya Law Reports judgments')
    parser.add_argument('--output', default=JUDGMENT_DIR, help='Output directory')
    parser.add_argument('--no-resume', action='store_false', dest='resume', help='Do not resume from last position')
    parser.add_argument('--max-pages', type=int, help='Maximum number of pages to scrape')
    parser.add_argument('--start-page', type=int, default=1, help='Page to start scraping from')
    args = parser.parse_args()
    
    scraper = KenyaLawReportsScraper(
        output_dir=args.output,
        resume=args.resume,
        max_pages=args.max_pages,
        start_page=args.start_page
    )
    
    scraper.scrape()
