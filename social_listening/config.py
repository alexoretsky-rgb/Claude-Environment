"""
Central configuration for the accesso social listening agent.

Defines the markets, keywords, competitors, and sources to monitor.
Edit this file to tune signal collection without touching any logic.
"""

# ─── accesso markets ───────────────────────────────────────────────────────────
MARKETS = [
    "attractions",
    "theme parks",
    "amusement parks",
    "museums",
    "cultural institutions",
    "ski resorts",
    "live entertainment",
    "concerts",
    "sports venues",
    "zoos",
    "aquariums",
    "water parks",
]

# ─── Core product/solution keywords ────────────────────────────────────────────
PRODUCT_KEYWORDS = [
    "ticketing software",
    "ecommerce ticketing",
    "point of sale attractions",
    "POS system venue",
    "virtual queuing",
    "queue management",
    "guest experience technology",
    "visitor management",
    "attraction management software",
    "venue analytics",
    "revenue management attractions",
    "dynamic pricing ticketing",
    "contactless ticketing",
    "mobile ticketing",
    "season pass management",
    "membership management software",
    "timed entry",
    "capacity management",
    "operator dashboard",
    "AI decision intelligence",
    "demand forecasting attractions",
]

# ─── Pain point / operator sentiment keywords ───────────────────────────────────
PAIN_POINT_KEYWORDS = [
    "ticketing problems",
    "long lines",
    "wait times",
    "sold out",
    "booking issues",
    "visitor frustration",
    "overcrowding",
    "staff shortage",
    "labor costs venue",
    "revenue loss ticketing",
    "data silos",
    "legacy ticketing",
    "outdated POS",
    "technology upgrade",
    "digital transformation attractions",
    "post-pandemic recovery attractions",
    "attendance decline",
    "visitor experience complaints",
]

# ─── Competitors to monitor ─────────────────────────────────────────────────────
# Assumption: these are accesso's primary known competitors.
# Add/remove as competitive landscape shifts.
COMPETITORS = [
    "Tixtrack",
    "Siriusware",
    "ACME",
    "Gateway Ticketing",
    "Seatgeek Enterprise",
    "Momentus Technologies",
    "Envision",
    "VGS",
    "Etix",
    "TicketSocket",
    "Vivaticket",
    "Convious",
    "Palisis",
    "Betterez",
]

# ─── Reddit subreddits to monitor ──────────────────────────────────────────────
REDDIT_SUBREDDITS = [
    "AmusementParks",
    "ThemeParkDesign",
    "SkiResorts",
    "skiing",
    "snowboarding",
    "museums",
    "LiveMusic",
    "concerts",
    "eventprofs",      # event professionals community
    "SaaS",
    "b2bsales",
    "hospitality",
    "smallbusiness",
    "entrepreneur",
    "Ticketmaster",    # consumer frustration signal — captures language
]

# Posts per subreddit per collection run (Reddit rate limits: ~1 req/sec)
REDDIT_POST_LIMIT = 25

# ─── RSS feeds from industry publications ──────────────────────────────────────
RSS_FEEDS = [
    {
        "name": "Attractions Management",
        "url": "https://www.attractionsmanagement.com/rss.cfm",
        "market": "attractions",
    },
    {
        "name": "Blooloop",
        "url": "https://blooloop.com/feed/",
        "market": "attractions",
    },
    {
        "name": "Park World Magazine",
        "url": "https://parkworld-online.com/feed/",
        "market": "attractions",
    },
    {
        "name": "Museum Next",
        "url": "https://www.museumnext.com/feed/",
        "market": "museums",
    },
    {
        "name": "American Alliance of Museums Blog",
        "url": "https://www.aam-us.org/feed/",
        "market": "museums",
    },
    {
        "name": "Ski Area Management",
        "url": "https://saminfo.com/feed/",
        "market": "ski",
    },
    {
        "name": "Pollstar News",
        "url": "https://www.pollstar.com/feed",
        "market": "live_entertainment",
    },
    {
        "name": "Venues Now",
        "url": "https://www.venuesnow.com/feed/",
        "market": "live_entertainment",
    },
    {
        "name": "Eventbrite Business Blog",
        "url": "https://www.eventbrite.com/blog/feed/",
        "market": "events",
    },
    {
        "name": "Access Control & Security Systems",
        "url": "https://www.securitysales.com/feed/",
        "market": "venue_tech",
    },
]

# Max articles per feed per collection run
RSS_ARTICLE_LIMIT = 10

# ─── YouTube search queries ─────────────────────────────────────────────────────
# Requires YOUTUBE_API_KEY env var. Set to [] to disable.
YOUTUBE_QUERIES = [
    "attractions ticketing technology 2024",
    "theme park virtual queue system",
    "museum visitor experience technology",
    "ski resort reservation system",
    "live event ticketing challenges",
    "venue management software review",
    "attraction operator pain points",
    "queue management theme park",
    "contactless ticketing solution",
]

# Max YouTube videos per query per run
YOUTUBE_VIDEO_LIMIT = 5

# ─── Web search queries (via Claude's web_search tool) ─────────────────────────
WEB_SEARCH_QUERIES = [
    "attractions industry ticketing technology trends 2024 2025",
    "theme park operator technology challenges survey",
    "museum digital transformation visitor experience",
    "ski resort technology reservation system operator",
    "live entertainment venue technology pain points",
    "ticketing software B2B buyer frustrations",
    "virtual queuing guest experience ROI",
    "attraction POS system replacement buyers",
    "accesso competitor comparison review",
    "IAAPA technology trends operators",
    "venue analytics AI decision intelligence",
]

# Max results returned per web search query
WEB_SEARCH_RESULT_LIMIT = 5

# ─── Analysis configuration ─────────────────────────────────────────────────────

# Claude model for all analysis (adaptive thinking is enabled)
ANALYSIS_MODEL = "claude-opus-4-6"

# Model for quick classification tasks (cheaper, faster)
CLASSIFICATION_MODEL = "claude-haiku-4-5"

# How many raw signals to batch together for analysis
BATCH_SIZE = 20

# Minimum relevance score (0.0–1.0) to keep a signal after filtering
RELEVANCE_THRESHOLD = 0.4

# ─── Report configuration ───────────────────────────────────────────────────────

# How many days of signals to include in a weekly synthesis report
REPORT_LOOKBACK_DAYS = 7

# Number of top themes / pain points / opportunities to surface in report
TOP_N_THEMES = 8
TOP_N_PAIN_POINTS = 10
TOP_N_OPPORTUNITIES = 6
TOP_N_COMPETITOR_INSIGHTS = 5
