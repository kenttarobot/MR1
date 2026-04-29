import os
import time
import random
import requests
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

# ==========================================
# CONFIGURATION
# ==========================================

BASE_URL = "https://cdn.moltyroyale.com/api"
API_KEY = os.getenv("API_KEY")

# Timing Configuration
SCAN_DELAY = 10
ERROR_DELAY = 20
RETRY_DELAY = 5
MAX_RETRIES = 3
RATE_LIMIT_DELAY = 60

# Bot Configuration
BOT_NAME_PREFIX = "BOT"
MAX_ROOM_AGE_SECONDS = 300  # Ignore rooms older than 5 minutes

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "molty_bot.log"

if not API_KEY:
    raise Exception("API_KEY belum diisi. Set environment variable API_KEY")

# ==========================================
# ENUMS & CONSTANTS
# ==========================================

class GameStatus(Enum):
    WAITING = "waiting"
    OPEN = "open"
    PLAYING = "playing"
    FINISHED = "finished"

class EntryType(Enum):
    FREE = "free"
    PREMIUM = "premium"
    TOKEN = "token"

# ==========================================
# LOGGING SETUP
# ==========================================

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==========================================
# SESSION MANAGER
# ==========================================

class SessionManager:
    """Manage HTTP session with retry and rate limiting"""
    
    def __init__(self):
        self.session = requests.Session()
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 1  # Minimum 1 second between requests
    
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def get(self, url, **kwargs):
        """GET request with rate limiting"""
        self._rate_limit()
        return self.session.get(url, **kwargs)
    
    def post(self, url, **kwargs):
        """POST request with rate limiting"""
        self._rate_limit()
        return self.session.post(url, **kwargs)

session_manager = SessionManager()

# ==========================================
# HEADERS
# ==========================================

def get_headers() -> Dict[str, str]:
    """Generate request headers"""
    return {
        "X-API-Key": API_KEY,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://www.moltyroyale.com",
        "Referer": "https://www.moltyroyale.com/",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }

# ==========================================
# ROOM MANAGEMENT
# ==========================================

class RoomManager:
    """Handle room operations"""
    
    @staticmethod
    def parse_room_response(data: Any) -> List[Dict]:
        """Parse various response formats"""
        if isinstance(data, dict):
            # Check for common response structures
            if "data" in data:
                return data["data"] if isinstance(data["data"], list) else [data["data"]]
            if "games" in data:
                return data["games"] if isinstance(data["games"], list) else [data["games"]]
            if "rooms" in data:
                return data["rooms"] if isinstance(data["rooms"], list) else [data["rooms"]]
            # Single room object
            if "id" in data:
                return [data]
        
        if isinstance(data, list):
            return data
        
        return []
    
    @staticmethod
    def is_room_valid(room: Dict) -> bool:
        """Validate room data structure"""
        required_fields = ["id"]
        return all(field in room for field in required_fields)
    
    @staticmethod
    def get_room_age(room: Dict) -> Optional[float]:
        """Calculate room age in seconds"""
        if "createdAt" in room:
            try:
                created_time = datetime.fromisoformat(room["createdAt"].replace('Z', '+00:00'))
                return (datetime.now().astimezone() - created_time).total_seconds()
            except:
                pass
        return None
    
    @staticmethod
    def filter_rooms(rooms: List[Dict]) -> List[Dict]:
        """Filter and sort rooms based on criteria"""
        filtered = []
        
        for room in rooms:
            # Check if room is valid
            if not RoomManager.is_room_valid(room):
                continue
            
            # Check entry type
            entry_type = room.get("entryType", "")
            if entry_type != EntryType.FREE.value:
                continue
            
            # Check room status
            status = room.get("status", "")
            if status not in [GameStatus.WAITING.value, GameStatus.OPEN.value]:
                continue
            
            # Check availability
            agent_count = room.get("agentCount", 0)
            max_agents = room.get("maxAgents", 0)
            
            if agent_count >= max_agents:
                continue
            
            # Check room age (ignore old rooms)
            room_age = RoomManager.get_room_age(room)
            if room_age and room_age > MAX_ROOM_AGE_SECONDS:
                logger.debug(f"Room {room.get('id')} is too old ({room_age:.0f}s), skipping")
                continue
            
            filtered.append(room)
        
        # Sort by most empty first
        filtered.sort(key=lambda x: x.get("agentCount", 999))
        
        return filtered

# ==========================================
# API FUNCTIONS
# ==========================================

def get_rooms_with_retry() -> Optional[List[Dict]]:
    """Get rooms with retry mechanism"""
    endpoints = [
        "/games?status=waiting&limit=50",
        "/games?status=open&limit=50",
        "/games?limit=50"
    ]
    
    for attempt in range(MAX_RETRIES):
        for path in endpoints:
            try:
                logger.debug(f"Fetching rooms from {path} (attempt {attempt + 1})")
                
                response = session_manager.get(
                    BASE_URL + path,
                    headers=get_headers(),
                    timeout=15
                )
                
                # Handle different status codes
                if response.status_code == 429:  # Rate limited
                    logger.warning("Rate limited by server, waiting...")
                    time.sleep(RATE_LIMIT_DELAY)
                    continue
                
                if response.status_code == 403:  # Forbidden
                    logger.error("Access forbidden (403). Check API key or IP ban")
                    time.sleep(ERROR_DELAY)
                    continue
                
                if response.status_code == 503:  # Service unavailable
                    logger.warning("Service unavailable (503), waiting...")
                    time.sleep(RETRY_DELAY)
                    continue
                
                response.raise_for_status()
                
                data = response.json()
                rooms = RoomManager.parse_room_response(data)
                
                if rooms:
                    logger.info(f"Found {len(rooms)} rooms from {path}")
                    return rooms
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout fetching {path}")
                continue
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error fetching {path}")
                continue
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON response: {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error fetching {path}: {e}")
                continue
        
        if attempt < MAX_RETRIES - 1:
            logger.info(f"Retry {attempt + 1}/{MAX_RETRIES} in {RETRY_DELAY}s")
            time.sleep(RETRY_DELAY)
    
    return None

def join_room_with_retry(room_id: str, bot_name: str) -> bool:
    """Join room with retry mechanism"""
    payload = {
        "name": bot_name,
        "timestamp": datetime.now().isoformat()
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempting to join room {room_id} as {bot_name} (attempt {attempt + 1})")
            
            response = session_manager.post(
                f"{BASE_URL}/games/{room_id}/agents/register",
                json=payload,
                headers=get_headers(),
                timeout=15
            )
            
            # Handle specific status codes
            if response.status_code == 409:  # Conflict - already joined or room full
                logger.warning(f"Room {room_id} is full or already joined")
                return False
            
            if response.status_code == 404:  # Not found
                logger.warning(f"Room {room_id} not found")
                return False
            
            if response.status_code == 429:  # Rate limited
                logger.warning("Rate limited, waiting before retry...")
                time.sleep(RATE_LIMIT_DELAY)
                continue
            
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully joined room {room_id}")
            logger.debug(f"Response: {json.dumps(result, indent=2)}")
            
            return True
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout joining room {room_id}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error joining room {room_id}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response when joining: {e}")
        except Exception as e:
            logger.error(f"Unexpected error joining room {room_id}: {e}")
        
        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY)
    
    return False

# ==========================================
# STATISTICS TRACKING
# ==========================================

class BotStatistics:
    """Track bot performance metrics"""
    
    def __init__(self):
        self.total_scans = 0
        self.total_rooms_found = 0
        self.total_joins_attempted = 0
        self.total_joins_successful = 0
        self.total_errors = 0
        self.start_time = datetime.now()
        self.joined_rooms = set()
    
    def increment_scans(self):
        self.total_scans += 1
    
    def add_rooms_found(self, count: int):
        self.total_rooms_found += count
    
    def add_join_attempt(self):
        self.total_joins_attempted += 1
    
    def add_join_success(self, room_id: str):
        self.total_joins_successful += 1
        self.joined_rooms.add(room_id)
    
    def add_error(self):
        self.total_errors += 1
    
    def get_stats(self) -> Dict:
        runtime = (datetime.now() - self.start_time).total_seconds()
        success_rate = (self.total_joins_successful / self.total_joins_attempted * 100) if self.total_joins_attempted > 0 else 0
        
        return {
            "runtime_seconds": runtime,
            "total_scans": self.total_scans,
            "total_rooms_found": self.total_rooms_found,
            "total_join_attempts": self.total_joins_attempted,
            "total_join_success": self.total_joins_successful,
            "success_rate": f"{success_rate:.2f}%",
            "total_errors": self.total_errors,
            "unique_rooms_joined": len(self.joined_rooms)
        }
    
    def print_stats(self):
        """Print current statistics"""
        stats = self.get_stats()
        logger.info("=" * 50)
        logger.info("BOT STATISTICS")
        logger.info("=" * 50)
        logger.info(f"Runtime: {stats['runtime_seconds']:.0f} seconds")
        logger.info(f"Scans performed: {stats['total_scans']}")
        logger.info(f"Total rooms found: {stats['total_rooms_found']}")
        logger.info(f"Join attempts: {stats['total_join_attempts']}")
        logger.info(f"Successful joins: {stats['total_join_success']}")
        logger.info(f"Success rate: {stats['success_rate']}")
        logger.info(f"Errors encountered: {stats['total_errors']}")
        logger.info(f"Unique rooms joined: {stats['unique_rooms_joined']}")
        logger.info("=" * 50)

stats = BotStatistics()

# ==========================================
# MAIN BOT LOGIC
# ==========================================

def generate_bot_name() -> str:
    """Generate random bot name"""
    adjectives = ["Fast", "Smart", "Quick", "Brave", "Swift", "Clever"]
    nouns = ["Player", "Gamer", "Hunter", "Warrior", "Knight", "Ranger"]
    
    if random.random() < 0.3:  # 30% chance for simple name
        return f"{BOT_NAME_PREFIX}-{random.randint(1000, 9999)}"
    else:
        return f"{random.choice(adjectives)}{random.choice(nouns)}{random.randint(10, 99)}"

def run_bot():
    """Main bot loop"""
    logger.info("=" * 50)
    logger.info("MOLTY ROYALE AUTO JOIN BOT")
    logger.info("=" * 50)
    logger.info(f"API URL: {BASE_URL}")
    logger.info(f"Scan delay: {SCAN_DELAY}s")
    logger.info(f"Error delay: {ERROR_DELAY}s")
    logger.info(f"Max retries: {MAX_RETRIES}")
    logger.info("=" * 50)
    
    last_stats_time = time.time()
    stats_interval = 300  # Print stats every 5 minutes
    
    while True:
        try:
            stats.increment_scans()
            logger.info(f"Scanning for rooms... (Scan #{stats.total_scans})")
            
            rooms = get_rooms_with_retry()
            
            if not rooms:
                logger.warning("No rooms found in response")
                time.sleep(ERROR_DELAY)
                continue
            
            stats.add_rooms_found(len(rooms))
            logger.info(f"Found {len(rooms)} total rooms")
            
            # Filter valid rooms
            valid_rooms = RoomManager.filter_rooms(rooms)
            
            if not valid_rooms:
                logger.info("No suitable free rooms available")
                time.sleep(SCAN_DELAY)
                continue
            
            logger.info(f"Found {len(valid_rooms)} suitable free rooms")
            
            # Try to join the best room
            target_room = valid_rooms[0]
            room_id = target_room["id"]
            room_name = target_room.get("name", room_id)
            current_players = target_room.get("agentCount", 0)
            max_players = target_room.get("maxAgents", 0)
            
            logger.info(f"Targeting room: {room_name}")
            logger.info(f"Players: {current_players}/{max_players}")
            logger.info(f"Entry type: {target_room.get('entryType', 'unknown')}")
            
            # Generate bot name
            bot_name = generate_bot_name()
            logger.info(f"Bot name: {bot_name}")
            
            stats.add_join_attempt()
            
            if join_room_with_retry(room_id, bot_name):
                stats.add_join_success(room_id)
                logger.info(f"✅ Successfully joined room {room_name}")
                
                # After successful join, wait longer to avoid spam
                time.sleep(SCAN_DELAY * 2)
            else:
                logger.error(f"❌ Failed to join room {room_name}")
                time.sleep(SCAN_DELAY)
            
            # Print statistics periodically
            if time.time() - last_stats_time >= stats_interval:
                stats.print_stats()
                last_stats_time = time.time()
            
        except KeyboardInterrupt:
            logger.info("\nBot stopped by user")
            stats.print_stats()
            break
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            stats.add_error()
            time.sleep(ERROR_DELAY)

# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("\nBot terminated")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
