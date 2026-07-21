"""
Bootstrap the first admin user.

Run this once after setting JWT_SECRET in your .env:

    python create_admin.py

The script prompts for a username and password, validates password strength,
and writes the user to data/users.db.
"""
import getpass
import sys
from pathlib import Path

# Ensure the project root is on sys.path so 'backend' package is importable.
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from backend.config import DB_PATH, JWT_SECRET
from backend.auth import init_db, create_user, get_user_by_username, validate_password_strength

if not JWT_SECRET:
    print(
        "\n[ERROR] JWT_SECRET is not set in your .env file.\n"
        "Generate one with:  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "Then add it to .env as:  JWT_SECRET=<your_secret>\n"
    )
    sys.exit(1)

init_db()

print(f"\nUser database: {DB_PATH}\n")

username = input("New admin username: ").strip().lower()
if not username:
    print("[ERROR] Username cannot be empty.")
    sys.exit(1)

if get_user_by_username(username):
    print(f"[ERROR] User '{username}' already exists.")
    sys.exit(1)

while True:
    password = getpass.getpass("Password (min 10 chars, 1 uppercase, 1 digit): ")
    confirm  = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("  Passwords do not match. Try again.")
        continue
    try:
        validate_password_strength(password)
    except Exception as exc:
        print(f"  {exc.detail}")
        continue
    break

uid = create_user(username, password, is_admin=True)
print(f"\n[OK] Admin user '{username}' created (id={uid}).")
print("You can now start the server and log in.\n")
