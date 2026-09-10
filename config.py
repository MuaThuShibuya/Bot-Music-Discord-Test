import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# SSL certificates on macOS / Python.org builds
if os.name != 'nt':  # Bỏ qua nếu chạy trên Windows (nt = Windows)
    os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')
    os.environ.setdefault('SSL_CERT_DIR', '/etc/ssl')

# ============================================
# Application Configuration
# ============================================
APP_NAME = os.getenv('APP_NAME', 'Discord Bot')

# ============================================
# Discord Bot Configuration
# ============================================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
BOT_PREFIX = os.getenv('BOT_PREFIX', '!')
SUPPORT_SERVER_URL = os.getenv('SUPPORT_SERVER_URL', 'https://discord.com')
PROFILE_HOUR_RATE_VND = int(os.getenv('PROFILE_HOUR_RATE_VND', '0'))

# Parse DISCORD_OWNER_IDS (comma-separated)
DISCORD_OWNER_IDS_STR = os.getenv('DISCORD_OWNER_IDS', '')
DISCORD_OWNER_IDS = [
    int(owner_id.strip()) 
    for owner_id in DISCORD_OWNER_IDS_STR.split(',') 
    if owner_id.strip().isdigit()
]

# ============================================
# Admin Information (Optional)
# ============================================
ADMIN_ID = os.getenv('ADMIN_ID', '0')
if ADMIN_ID != '0':
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        ADMIN_ID = 0

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', '')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', '')

# ============================================
# Paths
# ============================================
DATABASE_DIR = os.path.join(BASE_DIR, 'database')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
COGS_DIR = os.path.join(BASE_DIR, 'cogs')

# ============================================
# Validation
# ============================================
if not DISCORD_TOKEN:
    raise ValueError("❌ DISCORD_TOKEN không được để trống trong .env!")

if not DISCORD_TOKEN.startswith('your_'):
    print(f"✅ Bot name: {APP_NAME}")
    print(f"✅ Owner IDs: {DISCORD_OWNER_IDS}")
    print(f"✅ Prefix: {BOT_PREFIX}")
