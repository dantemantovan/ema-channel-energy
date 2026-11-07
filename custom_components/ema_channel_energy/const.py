"""Constants for EMA Channel Energy."""

DOMAIN = "ema_channel_energy"
VERSION = "0.1.0"

# Official base URL from the APsystems OpenAPI end-user manual (section 2.4).
# Deliberately not user-configurable so credentials are only ever sent here.
BASE_URL = "https://api.apsystemsema.com:9282"

CONF_APP_ID = "app_id"
CONF_APP_SECRET = "app_secret"
CONF_SID = "sid"
CONF_ECU_ID = "ecu_id"

# Daily fetch of the previous, completed local day.
FETCH_HOUR = 0
FETCH_MINUTE = 45
RETRY_DELAY_HOURS = 2
MAX_ATTEMPTS_PER_DAY = 3          # scheduled + retries for one target date
MANUAL_MIN_INTERVAL_MIN = 15      # manual refresh button throttle
LIMIT_BACKOFF_HOURS = 24          # after a quota / rate-limit response
REQUEST_TIMEOUT_S = 30

# Response codes (manual Annex 1, as also handled by community clients).
CODE_OK = 0
API_LIMIT_CODES = frozenset({2005, 7001, 7002, 7003})
AUTH_ERROR_CODES = frozenset({4000})

STORAGE_VERSION = 1
