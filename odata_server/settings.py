import os

MONGO_SEARCH_MAX_TIME_MS = int(os.getenv("MONGO_SEARCH_MAX_TIME_MS", "30000"))
