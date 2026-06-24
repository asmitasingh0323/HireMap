import os
from dotenv import load_dotenv

load_dotenv()

print("ADZUNA_APP_ID:", repr(os.getenv("ADZUNA_APP_ID")))
print("ADZUNA_APP_KEY length:", len(os.getenv("ADZUNA_APP_KEY") or ""))
print("DB_USER:", repr(os.getenv("DB_USER")))
print("DB_PASSWORD:", repr(os.getenv("DB_PASSWORD")))
print("DB_HOST:", repr(os.getenv("DB_HOST")))
