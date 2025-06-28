import imaplib
import email
import re
import requests
import time
import logging
import random
import os
from bs4 import BeautifulSoup
from urllib.parse import unquote
from requests.exceptions import ConnectionError, Timeout, RequestException
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SteamTradeAutoAccepter:
    def __init__(self, email_config, allowed_traders):
        """
        Initialize the Steam Trade Auto Accepter
        
        Args:
            email_config (dict): Email configuration with keys: server, username, password
            allowed_traders (list): List of allowed Steam profile URLs/IDs for auto-accept (required)
        """
        self.email_config = email_config
        self.allowed_traders = allowed_traders
        self.session = requests.Session()
        
        # Enhanced session headers to appear more like a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Configure session with retry adapter
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Language detection patterns
        self.language_patterns = {
            'german': {
                'trade_confirmation': ['handelsbest', 'handelsangebot'],
                'hello': ['hallo'],
                'your_items': ['ihre gegenstände', 'ihre items'],
                'their_items': ['gegenstände von', 'items von'],
                'no_items_selected': ['haben keine gegenstände', 'keine gegenstände zum austausch'],
                'not_friends': ['sind mit diesem nutzer nicht befreundet', 'nicht befreundet'],
                'friends_since': ['auf steam seit dem', 'ist auf steam seit'],
                'steam_level': ['hat steam-level', 'steam-level'],
                'send_offer': ['handelsangebot senden'],
                'cancel_trade': ['handel annullieren', 'annullieren'],
                'success_indicators': ['handel wurde akzeptiert', 'erfolgreich', 'bestätigt'],
                'error_indicators': ['fehler', 'ungültig', 'abgelaufen', 'nicht gefunden', 'fehlgeschlagen']
            },
            'english': {
                'trade_confirmation': ['trade confirmation', 'trade offer'],
                'hello': ['hello', 'hi'],
                'your_items': ['your items', 'items you'],
                'their_items': ['items from', 'their items'],
                'no_items_selected': ['you have not selected any items', 'no items selected'],
                'not_friends': ['you are not friends', 'not friends with'],
                'friends_since': ['you\'ve been friends since', 'friends since'],
                'steam_level': ['steam level', 'level'],
                'send_offer': ['send trade offer', 'accept trade'],
                'cancel_trade': ['cancel trade', 'decline'],
                'success_indicators': ['trade has been accepted', 'successfully', 'confirmed', 'trade offer accepted'],
                'error_indicators': ['error', 'invalid', 'expired', 'not found', 'failed']
            }
        }
        
        logger.info(f"Initialized auto-accepter for traders: {self.allowed_traders}")
        logger.info("✅ Multi-language support enabled (German/English)")
        
    def detect_email_language(self, subject, body):
        """Detect the language of the email based on subject and body content"""
        text_to_check = (subject + " " + body).lower()
        
        # Check for German patterns first
        german_matches = 0
        english_matches = 0
        
        for pattern_list in self.language_patterns['german'].values():
            for pattern in pattern_list:
                if pattern.lower() in text_to_check:
                    german_matches += 1
                    
        for pattern_list in self.language_patterns['english'].values():
            for pattern in pattern_list:
                if pattern.lower() in text_to_check:
                    english_matches += 1
        
        if german_matches > english_matches:
            return 'german'
        else:
            return 'english'  # Default to English
    
    def connect_to_email(self):
        """Connect to email server and return IMAP connection"""
        try:
            mail = imaplib.IMAP4_SSL(self.email_config['server'])
            mail.login(self.email_config['username'], self.email_config['password'])
            logger.info("Successfully connected to email")
            return mail
        except Exception as e:
            logger.error(f"Failed to connect to email: {e}")
            return None
    
    def get_trade_offer_emails(self, mail):
        """Fetch unread Steam trade offer emails"""
        try:
            mail.select('inbox')
            
            # Search for unread emails from Steam about trade offers
            status, messages = mail.search(None, '(UNSEEN FROM "noreply@steampowered.com")')
            
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            trade_offers = []
            
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                    
                msg = email.message_from_bytes(msg_data[0][1])
                subject = msg['Subject']
                
                # Decode subject if it's encoded
                if '=?UTF-8?B?' in subject:
                    import base64
                    encoded_part = subject.split('=?UTF-8?B?')[1].split('?=')[0]
                    try:
                        decoded_subject = base64.b64decode(encoded_part).decode('utf-8')
                        subject = decoded_subject
                    except:
                        pass  # Keep original subject if decoding fails
                
                # Check if it's a trade offer email (support both languages)
                subject_lower = subject.lower()
                is_trade_email = (
                    ('trade' in subject_lower and ('confirmation' in subject_lower or 'offer' in subject_lower)) or
                    ('handel' in subject_lower and ('bestätigung' in subject_lower or 'angebot' in subject_lower))
                )
                
                if is_trade_email:
                    # Extract email body
                    body = self.get_email_body(msg)
                    language = self.detect_email_language(subject, body)
                    trade_data = self.parse_trade_email(body, language)
                    
                    if trade_data:
                        trade_offers.append({
                            'email_id': email_id,
                            'subject': subject,
                            'trade_data': trade_data,
                            'language': language,
                            'raw_body': body
                        })
                        logger.info(f"Found trade offer email ({language}): {subject}")
            
            return trade_offers
            
        except Exception as e:
            logger.error(f"Error fetching trade offer emails: {e}")
            return []
    
    def get_email_body(self, msg):
        """Extract email body from message"""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    body = part.get_payload(decode=True).decode('utf-8')
                    break
                elif part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8')
        else:
            body = msg.get_payload(decode=True).decode('utf-8')
        
        return body
    
    def parse_trade_email(self, body, language='english'):
        """Parse trade offer email to extract relevant information with multi-language support"""
        try:
            soup = BeautifulSoup(body, 'html.parser')
            
            trade_data = {
                'trader_name': 'Unknown',
                'trader_profile': None,
                'trader_avatar': None,
                'trader_level': 'Unknown',
                'friendship_date': 'Unknown',
                'friendship_status': 'Unknown',
                'your_items': [],
                'their_items': [],
                'confirm_url': None,
                'cancel_url': None,
                'trade_id': None,
                'is_trusted_trader': False,
                'is_donation': False,
                'language': language
            }
            
            logger.info(f"🌍 Parsing {language} trade email")
            
            # Extract trader name and profile
            trader_links = soup.find_all('a', href=re.compile(r'steamcommunity\.com/(id|profiles)/'))
            if trader_links:
                for link in trader_links:
                    href = link.get('href')
                    if href and any(allowed_trader in href for allowed_trader in self.allowed_traders):
                        trade_data['trader_name'] = link.get_text().strip()
                        trade_data['trader_profile'] = href
                        trade_data['is_trusted_trader'] = True
                        logger.info(f"Found trusted trader: {trade_data['trader_name']} - {href}")
                        break
                    elif href and ('steamcommunity.com/id/' in href or 'steamcommunity.com/profiles/' in href):
                        # Still extract info but mark as untrusted
                        trade_data['trader_name'] = link.get_text().strip()
                        trade_data['trader_profile'] = href
                        logger.warning(f"Found UNTRUSTED trader: {trade_data['trader_name']} - {href}")
                        break
            
            # Extract trader avatar
            avatar_imgs = soup.find_all('img', src=re.compile(r'avatars\..*steamstatic\.com'))
            if avatar_imgs:
                trade_data['trader_avatar'] = avatar_imgs[0].get('src')
            
            # Extract trader level (works for both languages)
            level_spans = soup.find_all('span', class_='friendPlayerLevelNum')
            if level_spans:
                trade_data['trader_level'] = level_spans[0].get_text().strip()
            
            # Extract friendship status and date based on language
            text_content = soup.get_text().lower()
            
            if language == 'german':
                # Check friendship status in German
                if any(pattern in text_content for pattern in self.language_patterns['german']['not_friends']):
                    trade_data['friendship_status'] = 'Not friends'
                
                # Extract friendship date in German
                friend_patterns = [
                    r"auf steam seit dem\s*(\d+\.\s*\w+\s*\d+)",
                    r"ist auf steam seit\s*(\d+\.\s*\w+\s*\d+)"
                ]
                for pattern in friend_patterns:
                    match = re.search(pattern, text_content)
                    if match:
                        trade_data['friendship_date'] = match.group(1)
                        break
            else:
                # English patterns
                if any(pattern in text_content for pattern in self.language_patterns['english']['not_friends']):
                    trade_data['friendship_status'] = 'Not friends'
                
                friend_match = re.search(r"you've been friends since.*?(\d+\s+\w+)", text_content)
                if friend_match:
                    trade_data['friendship_date'] = friend_match.group(1)
            
            # Extract items (works for both languages as it uses HTML structure)
            self._extract_items(soup, trade_data, language)
            
            # Extract confirm and cancel URLs
            confirm_links = soup.find_all('a', href=re.compile(r'tradeoffer/\d+/confirm'))
            for link in confirm_links:
                href = link.get('href')
                if 'cancel=1' in href:
                    trade_data['cancel_url'] = href
                else:
                    trade_data['confirm_url'] = href
                    
                    # Extract trade ID
                    trade_id_match = re.search(r'tradeoffer/(\d+)/', href)
                    if trade_id_match:
                        trade_data['trade_id'] = trade_id_match.group(1)
            
            return trade_data
            
        except Exception as e:
            logger.error(f"Error parsing trade email: {e}")
            return None
    
    def _extract_items(self, soup, trade_data, language):
        """Extract items from trade email HTML"""
        try:
            # Look for item tables
            all_tables = soup.find_all('table')
            
            # Find tables containing items based on context
            for table in all_tables:
                table_text = table.get_text().lower()
                
                # Check if this is "your items" section
                is_your_items = False
                if language == 'german':
                    is_your_items = any(pattern in table_text for pattern in ['ihre gegenstände', 'ihre items'])
                else:
                    is_your_items = 'your items' in table_text
                
                if is_your_items:
                    items = self._extract_items_from_table(table)
                    trade_data['your_items'] = items
                    logger.info(f"Found {len(items)} items you're giving")
                    continue
                
                # Check if this is "their items" section
                is_their_items = False
                if language == 'german':
                    is_their_items = any(pattern in table_text for pattern in ['gegenstände von', 'items von'])
                else:
                    is_their_items = any(pattern in table_text for pattern in ['items from', 'their items'])
                
                if is_their_items:
                    items = self._extract_items_from_table(table)
                    trade_data['their_items'] = items
                    logger.info(f"Found {len(items)} items you're receiving")
            
            # Check if it's a donation (no items in exchange)
            text_content = soup.get_text().lower()
            if language == 'german':
                is_donation = any(pattern in text_content for pattern in self.language_patterns['german']['no_items_selected'])
            else:
                is_donation = any(pattern in text_content for pattern in self.language_patterns['english']['no_items_selected'])
            
            trade_data['is_donation'] = is_donation
            
        except Exception as e:
            logger.error(f"Error extracting items: {e}")
    
    def _extract_items_from_table(self, table):
        """Extract individual items from a table"""
        items = []
        try:
            # Find item images
            item_imgs = table.find_all('img', src=re.compile(r'steamstatic\.com/economy/image/'))
            
            # Find item names (looking for div elements with item names)
            item_name_divs = table.find_all('div', style=re.compile(r'color:\s*#D2D2D2'))
            item_names = []
            for div in item_name_divs:
                text = div.get_text().strip()
                if text and len(text) > 3:  # Filter out very short text
                    item_names.append(text)
            
            # Match images with names
            for i, img in enumerate(item_imgs):
                item_data = {
                    'name': item_names[i] if i < len(item_names) else 'Unknown Item',
                    'image': img.get('src'),
                    'index': i
                }
                items.append(item_data)
                
        except Exception as e:
            logger.error(f"Error extracting individual items: {e}")
        
        return items
    
    def is_trader_allowed(self, trade_data):
        """Check if the trader is in the allowed list for auto-accept"""
        if not trade_data.get('trader_profile'):
            logger.warning("No trader profile found, rejecting auto-accept")
            return False
            
        trader_profile = trade_data['trader_profile']
        
        # Check if trader profile contains any of the allowed trader IDs
        for allowed_trader in self.allowed_traders:
            if allowed_trader in trader_profile:
                logger.info(f"✅ TRUSTED TRADER: {trader_profile} matches allowed trader: {allowed_trader}")
                return True
        
        logger.warning(f"❌ UNTRUSTED TRADER: {trader_profile} not in allowed list: {self.allowed_traders}")
        return False
    
    def accept_trade(self, confirm_url, max_retries=3, language='english'):
        """Accept a trade offer by visiting the confirmation URL with retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to accept trade (attempt {attempt + 1}/{max_retries}): {confirm_url}")
                
                # Add some randomized delay to avoid rate limiting
                if attempt > 0:
                    delay = random.uniform(5, 15)
                    logger.info(f"⏳ Waiting {delay:.1f} seconds before retry...")
                    time.sleep(delay)
                
                # Visit the confirmation URL with increased timeout
                response = self.session.get(confirm_url, timeout=45)
                
                if response.status_code == 200:
                    response_text = response.text.lower()
                    
                    # Get language-specific success/error indicators
                    success_indicators = self.language_patterns[language]['success_indicators']
                    error_indicators = self.language_patterns[language]['error_indicators']
                    
                    if any(indicator in response_text for indicator in success_indicators):
                        logger.info("✅ Trade accepted successfully!")
                        return True
                    elif any(indicator in response_text for indicator in error_indicators):
                        logger.error("❌ Trade acceptance failed - error in response")
                        if attempt < max_retries - 1:
                            logger.info(f"🔄 Will retry in a moment...")
                            continue
                        return False
                    else:
                        logger.info("✅ Trade confirmation URL visited successfully")
                        return True
                else:
                    logger.error(f"❌ Failed to accept trade: HTTP {response.status_code}")
                    if attempt < max_retries - 1:
                        logger.info(f"🔄 Will retry with different approach...")
                        continue
                    return False
                    
            except (ConnectionError, Timeout) as e:
                logger.error(f"❌ Connection error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    delay = random.uniform(10, 30)  # Longer delay for connection issues
                    logger.info(f"🔄 Connection failed, waiting {delay:.1f} seconds before retry...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"❌ All {max_retries} attempts failed due to connection issues")
                    return False
                    
            except RequestException as e:
                logger.error(f"❌ Request error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Request failed, will retry...")
                    continue
                return False
                
            except Exception as e:
                logger.error(f"❌ Unexpected error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"🔄 Unexpected error, will retry...")
                    continue
                return False
        
        logger.error(f"❌ Failed to accept trade after {max_retries} attempts")
        return False
    
    def mark_email_as_read(self, mail, email_id):
        """Mark email as read"""
        try:
            mail.store(email_id, '+FLAGS', '\\Seen')
            logger.info("Email marked as read")
            return True
        except Exception as e:
            logger.error(f"Failed to mark email as read: {e}")
            return False
    
    def process_trade_offers(self, trade_offers, mail):
        """Process all trade offers - auto-accept from trusted traders"""
        processed_count = 0
        accepted_count = 0
        
        for offer in trade_offers:
            logger.info(f"Processing trade offer ({offer.get('language', 'unknown')}): {offer['subject']}")
            trade_data = offer['trade_data']
            offer_language = offer.get('language', 'english')
            
            # Security check: Only auto-accept from trusted traders
            if not self.is_trader_allowed(trade_data):
                logger.warning(f"🛡️ SECURITY: Trade from {trade_data.get('trader_name', 'Unknown')} ({trade_data.get('trader_profile', 'No profile')}) REJECTED - not in allowed traders list")
                self.mark_email_as_read(mail, offer['email_id'])
                processed_count += 1
                continue
            
            # Log trade details for trusted trader
            logger.info(f"🎮 TRUSTED TRADE DETAILS ({offer_language.upper()}):")
            logger.info(f"   Trader: {trade_data.get('trader_name', 'Unknown')}")
            logger.info(f"   Profile: {trade_data.get('trader_profile', 'Unknown')}")
            logger.info(f"   Level: {trade_data.get('trader_level', 'Unknown')}")
            logger.info(f"   Friendship: {trade_data.get('friendship_status', 'Unknown')}")
            logger.info(f"   Member since: {trade_data.get('friendship_date', 'Unknown')}")
            logger.info(f"   Your items: {len(trade_data.get('your_items', []))} items")
            logger.info(f"   Their items: {len(trade_data.get('their_items', []))} items")
            logger.info(f"   Is donation: {trade_data.get('is_donation', False)}")
            
            # Show your items
            if trade_data.get('your_items'):
                logger.info(f"   📤 Items you're giving:")
                for item in trade_data['your_items']:
                    logger.info(f"      • {item['name']}")
            
            # Show their items
            if trade_data.get('their_items'):
                logger.info(f"   📥 Items you're receiving:")
                for item in trade_data['their_items']:
                    logger.info(f"      • {item['name']}")
            
            # Attempt to accept the trade
            if trade_data.get('confirm_url'):
                logger.info(f"🚀 AUTO-ACCEPTING trade from trusted trader...")
                
                # Use enhanced accept_trade method with retries and language support
                if self.accept_trade(trade_data['confirm_url'], max_retries=3, language=offer_language):
                    logger.info(f"✅ Successfully accepted trade {trade_data.get('trade_id', 'Unknown ID')}")
                    accepted_count += 1
                else:
                    logger.error(f"❌ Failed to accept trade {trade_data.get('trade_id', 'Unknown ID')} after all retry attempts")
                
                # Always mark email as read to avoid reprocessing
                self.mark_email_as_read(mail, offer['email_id'])
                processed_count += 1
            else:
                logger.error(f"❌ No confirmation URL found for trade")
                self.mark_email_as_read(mail, offer['email_id'])
                processed_count += 1
        
        return processed_count, accepted_count
    
    def run(self, check_interval=60):
        """Main loop to check for and auto-accept trade offers"""
        logger.info("🚀 Starting Enhanced Steam Trade Auto-Accepter (Multi-Language Version)...")
        logger.info(f"📧 Monitoring email: {self.email_config['username']}")
        logger.info(f"🛡️ Trusted traders: {self.allowed_traders}")
        logger.info(f"⏰ Check interval: {check_interval} seconds")
        logger.info(f"🌍 Supported languages: German (Deutsch), English")
        logger.info(f"🔄 Enhanced with retry logic and better error handling")
        logger.info("=" * 60)
        
        while True:
            try:
                # Connect to email
                mail = self.connect_to_email()
                if not mail:
                    logger.error("Could not connect to email, retrying in 60 seconds...")
                    time.sleep(60)
                    continue
                
                # Get trade offer emails
                trade_offers = self.get_trade_offer_emails(mail)
                
                if not trade_offers:
                    logger.info("No new trade offer emails found")
                else:
                    logger.info(f"📬 Found {len(trade_offers)} trade offer email(s)")
                    processed, accepted = self.process_trade_offers(trade_offers, mail)
                    logger.info(f"✅ Processed {processed} emails, auto-accepted {accepted} trades")
                
                # Close email connection
                mail.close()
                mail.logout()
                
                # Wait before next check
                logger.info(f"⏳ Waiting {check_interval} seconds before next check...")
                logger.info("=" * 60)
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Stopping Steam Trade Auto-Accepter...")
                break
            except Exception as e:
                logger.error(f"💥 Unexpected error: {e}")
                time.sleep(60)  # Wait a minute before retrying

def get_env_config():
    """Get configuration from environment variables"""
    email_config = {
        'server': os.getenv('EMAIL_SERVER', 'imap.gmail.com'),
        'username': os.getenv('EMAIL_USERNAME'),
        'password': os.getenv('EMAIL_PASSWORD')
    }
    
    # Parse allowed traders from environment variable
    allowed_traders_env = os.getenv('ALLOWED_TRADERS')
    if allowed_traders_env:
        allowed_traders = [trader.strip() for trader in allowed_traders_env.split(',') if trader.strip()]
    else:
        allowed_traders = None
    
    # Get check interval from environment
    check_interval = int(os.getenv('CHECK_INTERVAL', '300'))  # Default 5 minutes
    
    return email_config, allowed_traders, check_interval

def main():
    logger.info("🐳 Starting Steam Trade Auto-Accepter in Docker (Multi-Language)...")
    
    # Get configuration from environment variables
    email_config, allowed_traders, check_interval = get_env_config()
    
    # Log configuration (but not password)
    logger.info(f"📧 Email Server: {email_config['server']}")
    logger.info(f"📧 Email Username: {email_config['username']}")
    logger.info(f"🛡️ Allowed Traders: {allowed_traders}")
    logger.info(f"⏰ Check Interval: {check_interval} seconds")
    logger.info(f"🌍 Multi-Language Support: German, English")
    
    # Validate configuration
    if not email_config['username']:
        logger.error("❌ EMAIL_USERNAME environment variable is required!")
        return
    
    if not email_config['password']:
        logger.error("❌ EMAIL_PASSWORD environment variable is required!")
        return
    
    if not allowed_traders:
        logger.error("❌ No allowed traders specified!")
        logger.error("Please set ALLOWED_TRADERS environment variable")
        logger.error("Example: ALLOWED_TRADERS='/id/trader1,/id/trader2'")
        return
    
    # Create and run the auto-accepter
    auto_accepter = SteamTradeAutoAccepter(email_config, allowed_traders)
    auto_accepter.run(check_interval=check_interval)

if __name__ == "__main__":
    main()