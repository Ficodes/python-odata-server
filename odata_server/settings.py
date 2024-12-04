# Copyright (c) 2024 Future Internet Consulting and Development Solutions S.L.

import os

MONGO_COUNT_MAX_TIME_MS = int(
    os.getenv(
        "ODATA_SERVER_MONGO_COUNT_MAX_TIME_MS",
        os.getenv("ODATA_SERVER_MONGO_SEARCH_MAX_TIME_MS", "30000"),
    )
)
MONGO_SEARCH_MAX_TIME_MS = int(
    os.getenv("ODATA_SERVER_MONGO_SEARCH_MAX_TIME_MS", "30000")
)
