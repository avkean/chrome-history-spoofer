"""
FastAPI backend for Chrome History Generator webapp.
Provides an API endpoint to generate spoofed Chrome history databases.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import random
import re
import sqlite3
import string
import tempfile
import urllib.parse
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

app = FastAPI(
    title="Chrome History Generator",
    description="Generate spoofed Chrome browser history for CTF challenges",
    version="1.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# CONSTANTS AND HELPERS
# ============================================================================

SG_TZ_NAME = "Asia/Singapore"
EPOCH_1601_UTC = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)

# Chrome transition values - bitmasks
CORE_TRANSITION_LINK = 0
CORE_TRANSITION_TYPED = 1
TRANSITION_CHAIN_START = 0x10000000
TRANSITION_CHAIN_END = 0x20000000
TRANSITION_FROM_ADDRESS_BAR = 0x00800000

TRANSITION_TYPED = CORE_TRANSITION_TYPED | TRANSITION_CHAIN_START | TRANSITION_CHAIN_END
TRANSITION_LINK = CORE_TRANSITION_LINK | TRANSITION_CHAIN_START | TRANSITION_CHAIN_END
TRANSITION_TYPED_FROM_BAR = TRANSITION_TYPED | TRANSITION_FROM_ADDRESS_BAR


def get_sg_tz() -> dt.tzinfo:
    return ZoneInfo(SG_TZ_NAME)


def to_chrome_time(tz_aware_dt: dt.datetime) -> int:
    if tz_aware_dt.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")
    utc = tz_aware_dt.astimezone(dt.timezone.utc)
    delta = utc - EPOCH_1601_UTC
    return int(delta.total_seconds() * 1_000_000)


def clamp(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def rand_urlsafe_id(rng: random.Random, n: int) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(rng.choice(alphabet) for _ in range(n))


def normalise_term(q: str) -> str:
    q = q.strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q


def google_search_url(q: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(q)


def google_search_title(q: str) -> str:
    return f"{q} - Google Search"


def docs_url(rng: random.Random, kind: str) -> str:
    doc_id = rand_urlsafe_id(rng, 44)
    if kind == "document":
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    if kind == "spreadsheets":
        return f"https://docs.google.com/spreadsheets/d/{doc_id}/edit"
    if kind == "presentation":
        return f"https://docs.google.com/presentation/d/{doc_id}/edit"
    return f"https://docs.google.com/{kind}/d/{doc_id}/edit"


def classroom_course_url(rng: random.Random) -> str:
    cid = rng.randint(100000000000, 999999999999)
    return f"https://classroom.google.com/u/0/c/{cid}"


def classroom_assignment_url(rng: random.Random, course_url: str) -> str:
    m = re.search(r"/c/(\d+)", course_url)
    cid = m.group(1) if m else str(rng.randint(100000000000, 999999999999))
    wid = rng.randint(100000000000, 999999999999)
    return f"https://classroom.google.com/u/0/c/{cid}/a/{wid}/details"


def sls_login_url() -> str:
    return "https://vle.learning.moe.edu.sg/login"


def mims_portal_url() -> str:
    return "https://mims.moe.gov.sg/"


def sls_module_url(rng: random.Random) -> str:
    mid = rng.randint(100000, 999999)
    return f"https://vle.learning.moe.edu.sg/learner/module/{mid}"


def youtube_search_url(query: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)


# ============================================================================
# DATABASE SCHEMA
# ============================================================================

MIN_SCHEMA_SQL = """
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;

CREATE TABLE IF NOT EXISTS meta(
  key LONGVARCHAR NOT NULL UNIQUE PRIMARY KEY,
  value LONGVARCHAR
);

CREATE TABLE IF NOT EXISTS urls(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url LONGVARCHAR,
  title LONGVARCHAR,
  visit_count INTEGER DEFAULT 0 NOT NULL,
  typed_count INTEGER DEFAULT 0 NOT NULL,
  last_visit_time INTEGER NOT NULL,
  hidden INTEGER DEFAULT 0 NOT NULL
);

CREATE TABLE IF NOT EXISTS visits(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url INTEGER NOT NULL,
  visit_time INTEGER NOT NULL,
  from_visit INTEGER,
  external_referrer_url TEXT,
  transition INTEGER DEFAULT 0 NOT NULL,
  segment_id INTEGER,
  visit_duration INTEGER DEFAULT 0 NOT NULL,
  incremented_omnibox_typed_score BOOLEAN DEFAULT FALSE NOT NULL,
  opener_visit INTEGER,
  originator_cache_guid TEXT,
  originator_visit_id INTEGER,
  originator_from_visit INTEGER,
  originator_opener_visit INTEGER,
  is_known_to_sync BOOLEAN DEFAULT FALSE NOT NULL,
  consider_for_ntp_most_visited BOOLEAN DEFAULT FALSE NOT NULL,
  visited_link_id INTEGER DEFAULT 0 NOT NULL,
  app_id TEXT
);

CREATE TABLE IF NOT EXISTS visit_source(
  id INTEGER PRIMARY KEY,
  source INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS keyword_search_terms(
  keyword_id INTEGER NOT NULL,
  url_id INTEGER NOT NULL,
  term LONGVARCHAR NOT NULL,
  normalized_term LONGVARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS downloads(
  id INTEGER PRIMARY KEY,
  guid VARCHAR NOT NULL,
  current_path LONGVARCHAR NOT NULL,
  target_path LONGVARCHAR NOT NULL,
  start_time INTEGER NOT NULL,
  received_bytes INTEGER NOT NULL,
  total_bytes INTEGER NOT NULL,
  state INTEGER NOT NULL,
  danger_type INTEGER NOT NULL,
  interrupt_reason INTEGER NOT NULL,
  hash BLOB NOT NULL,
  end_time INTEGER NOT NULL,
  opened INTEGER NOT NULL,
  last_access_time INTEGER NOT NULL,
  transient INTEGER NOT NULL,
  referrer VARCHAR NOT NULL,
  site_url VARCHAR NOT NULL,
  embedder_download_data VARCHAR NOT NULL,
  tab_url VARCHAR NOT NULL,
  tab_referrer_url VARCHAR NOT NULL,
  http_method VARCHAR NOT NULL,
  by_ext_id VARCHAR NOT NULL,
  by_ext_name VARCHAR NOT NULL,
  by_web_app_id VARCHAR NOT NULL,
  etag VARCHAR NOT NULL,
  last_modified VARCHAR NOT NULL,
  mime_type VARCHAR(255) NOT NULL,
  original_mime_type VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS downloads_url_chains(
  id INTEGER NOT NULL,
  chain_index INTEGER NOT NULL,
  url LONGVARCHAR NOT NULL,
  PRIMARY KEY (id, chain_index)
);

CREATE TABLE IF NOT EXISTS downloads_slices(
  download_id INTEGER NOT NULL,
  offset INTEGER NOT NULL,
  received_bytes INTEGER NOT NULL,
  finished INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (download_id, offset)
);

CREATE TABLE IF NOT EXISTS segments(
  id INTEGER PRIMARY KEY,
  name VARCHAR,
  url_id INTEGER NON NULL
);

CREATE TABLE IF NOT EXISTS segment_usage(
  id INTEGER PRIMARY KEY,
  segment_id INTEGER NOT NULL,
  time_slot INTEGER NOT NULL,
  visit_count INTEGER DEFAULT 0 NOT NULL
);

CREATE TABLE IF NOT EXISTS content_annotations(
  visit_id INTEGER PRIMARY KEY,
  visibility_score NUMERIC,
  floc_protected_score NUMERIC,
  categories VARCHAR,
  page_topics_model_version INTEGER,
  annotation_flags INTEGER NOT NULL,
  entities VARCHAR,
  related_searches VARCHAR,
  search_normalized_url VARCHAR,
  search_terms LONGVARCHAR,
  alternative_title VARCHAR,
  page_language VARCHAR,
  password_state INTEGER DEFAULT 0 NOT NULL,
  has_url_keyed_image BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS context_annotations(
  visit_id INTEGER PRIMARY KEY,
  context_annotation_flags INTEGER NOT NULL,
  duration_since_last_visit INTEGER,
  page_end_reason INTEGER,
  total_foreground_duration INTEGER,
  browser_type INTEGER DEFAULT 0 NOT NULL,
  window_id INTEGER DEFAULT -1 NOT NULL,
  tab_id INTEGER DEFAULT -1 NOT NULL,
  task_id INTEGER DEFAULT -1 NOT NULL,
  root_task_id INTEGER DEFAULT -1 NOT NULL,
  parent_task_id INTEGER DEFAULT -1 NOT NULL,
  response_code INTEGER DEFAULT 0 NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters(
  cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
  should_show_on_prominent_ui_surfaces BOOLEAN NOT NULL,
  label VARCHAR NOT NULL,
  raw_label VARCHAR NOT NULL,
  triggerability_calculated BOOLEAN NOT NULL,
  originator_cache_guid TEXT NOT NULL,
  originator_cluster_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clusters_and_visits(
  cluster_id INTEGER NOT NULL,
  visit_id INTEGER NOT NULL,
  score NUMERIC DEFAULT 0 NOT NULL,
  engagement_score NUMERIC DEFAULT 0 NOT NULL,
  url_for_deduping LONGVARCHAR NOT NULL,
  normalized_url LONGVARCHAR NOT NULL,
  url_for_display LONGVARCHAR NOT NULL,
  interaction_state INTEGER DEFAULT 0 NOT NULL,
  PRIMARY KEY(cluster_id, visit_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS cluster_keywords(
  cluster_id INTEGER NOT NULL,
  keyword VARCHAR NOT NULL,
  type INTEGER NOT NULL,
  score NUMERIC NOT NULL,
  collections VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_visit_duplicates(
  visit_id INTEGER NOT NULL,
  duplicate_visit_id INTEGER NOT NULL,
  PRIMARY KEY(visit_id, duplicate_visit_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS visited_links(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  link_url_id INTEGER NOT NULL,
  top_level_url LONGVARCHAR NOT NULL,
  frame_url LONGVARCHAR NOT NULL,
  visit_count INTEGER DEFAULT 0 NOT NULL
);

CREATE TABLE IF NOT EXISTS history_sync_metadata(
  storage_key INTEGER PRIMARY KEY NOT NULL,
  value BLOB
);

CREATE INDEX IF NOT EXISTS visits_url_index ON visits(url);
CREATE INDEX IF NOT EXISTS visits_from_index ON visits(from_visit);
CREATE INDEX IF NOT EXISTS visits_time_index ON visits(visit_time);
CREATE INDEX IF NOT EXISTS visits_originator_id_index ON visits(originator_visit_id);
CREATE INDEX IF NOT EXISTS urls_url_index ON urls(url);
CREATE INDEX IF NOT EXISTS keyword_search_terms_index1 ON keyword_search_terms(keyword_id, normalized_term);
CREATE INDEX IF NOT EXISTS keyword_search_terms_index2 ON keyword_search_terms(url_id);
CREATE INDEX IF NOT EXISTS keyword_search_terms_index3 ON keyword_search_terms(term);
CREATE INDEX IF NOT EXISTS segments_name ON segments(name);
CREATE INDEX IF NOT EXISTS segments_url_id ON segments(url_id);
CREATE INDEX IF NOT EXISTS segment_usage_time_slot_segment_id ON segment_usage(time_slot, segment_id);
CREATE INDEX IF NOT EXISTS segments_usage_seg_id ON segment_usage(segment_id);
CREATE INDEX IF NOT EXISTS cluster_keywords_cluster_id_index ON cluster_keywords(cluster_id);
CREATE INDEX IF NOT EXISTS clusters_for_visit ON clusters_and_visits(visit_id);
CREATE INDEX IF NOT EXISTS visited_links_index ON visited_links(link_url_id, top_level_url, frame_url);
"""


# ============================================================================
# DATA CLASSES AND CONTENT POOLS
# ============================================================================

@dataclass
class Page:
    url: str
    title: str
    typed: bool = False
    referrer: Optional[str] = None
    duration_s: int = 20


def build_academic_searches() -> List[Tuple[str, int]]:
    return [
        ("suvat equations examples", 12),
        ("kinematics graphs explained", 10),
        ("newton's laws of motion examples", 11),
        ("principle of moments questions", 9),
        ("pressure in liquids formula", 8),
        ("electromagnetic induction o level", 7),
        ("lens ray diagram convex concave", 8),
        ("wave equation v=fλ", 6),
        ("thermal physics heat capacity", 7),
        ("electricity series parallel circuit", 9),
        ("mole concept chemistry o level", 10),
        ("redox reaction examples", 8),
        ("acid base titration calculation", 9),
        ("organic chemistry alkanes alkenes", 7),
        ("electrolysis of brine", 6),
        ("differentiation chain rule a math", 11),
        ("integration by substitution", 9),
        ("trigonometry identities a math", 10),
        ("quadratic formula questions", 8),
        ("indices and surds rules", 7),
        ("probability tree diagram", 8),
        ("vectors addition questions", 7),
        ("logarithm rules and examples", 9),
        ("argumentative essay structure", 8),
        ("summary writing tips o level", 7),
        ("social studies singapore sbq", 9),
        ("python for loop examples", 8),
        ("o level exam format 2026", 7),
        ("how to study effectively for exams", 8),
        ("past year papers o level", 9),
    ]


def build_edu_youtube_videos() -> List[Tuple[str, str, int]]:
    return [
        ("Organic Chemistry in 30 Minutes", "edu", 8),
        ("A-Math Differentiation Full Revision", "edu", 10),
        ("Physics O-Level Electricity Explained", "edu", 11),
        ("How to Score A1 for O-Level Math", "edu", 9),
        ("Chemistry Mole Concept Made Easy", "edu", 10),
        ("Kinematics Explained - O Level Physics", "edu", 9),
        ("Newton's Laws Full Revision", "edu", 8),
        ("Acids Bases and Salts O Level", "edu", 8),
        ("Integration Techniques A Math", "edu", 9),
        ("Trigonometry Full Revision A Math", "edu", 10),
    ]


def pick_weighted(rng: random.Random, items: List[Tuple[Any, int]]) -> Any:
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for item, w in items:
        upto += w
        if r <= upto:
            return item
    return items[-1][0]


def pick_weighted_triple(rng: random.Random, items: List[Tuple[Any, Any, int]]) -> Tuple[Any, Any]:
    total = sum(w for _, _, w in items)
    r = rng.uniform(0, total)
    upto = 0.0
    for a, b, w in items:
        upto += w
        if r <= upto:
            return (a, b)
    return (items[-1][0], items[-1][1])


def youtube_edu_video(rng: random.Random) -> Tuple[str, str]:
    title, _ = pick_weighted_triple(rng, build_edu_youtube_videos())
    vid = rand_urlsafe_id(rng, 11)
    return (f"https://www.youtube.com/watch?v={vid}", title + " - YouTube")


def notion_url(rng: random.Random) -> Tuple[str, str]:
    page_id = rand_urlsafe_id(rng, 32)
    titles = ["Physics Notes - Notion", "Chemistry Revision - Notion", "A Math Notes - Notion", "Study Plan - Notion"]
    return (f"https://www.notion.so/{page_id}", rng.choice(titles))


def quizlet_url(rng: random.Random, topic: str) -> Tuple[str, str]:
    set_id = rng.randint(100000, 999999)
    slug = topic.lower().replace(" ", "-")[:30]
    return (f"https://quizlet.com/{set_id}/{slug}-flash-cards/", f"{topic} Flashcards | Quizlet")


def exam_papers_url(rng: random.Random) -> Tuple[str, str]:
    sites = [
        ("https://www.yoursingaporeantutor.com/past-papers/", "Free O Level Past Papers"),
        ("https://sgtestpaper.com/", "SG Test Paper - Free Exam Papers"),
    ]
    return rng.choice(sites)


# ============================================================================
# BROWSING FLOWS
# ============================================================================

def flow_homework_session(rng: random.Random) -> List[Page]:
    pages = []
    topic = pick_weighted(rng, build_academic_searches())
    
    if rng.random() < 0.6:
        course = classroom_course_url(rng)
        pages.append(Page("https://classroom.google.com/u/0/h", "Google Classroom", typed=True, duration_s=rng.randint(30, 90)))
        pages.append(Page(course, "Class - Google Classroom", referrer="https://classroom.google.com/u/0/h", duration_s=rng.randint(60, 180)))
        assign = classroom_assignment_url(rng, course)
        pages.append(Page(assign, "Assignment - Google Classroom", referrer=course, duration_s=rng.randint(60, 180)))
        doc = docs_url(rng, "document")
        pages.append(Page(doc, "Untitled document - Google Docs", referrer=assign, duration_s=rng.randint(300, 900)))
    else:
        pages.append(Page(sls_login_url(), "SLS Login", typed=True, duration_s=rng.randint(15, 45)))
        pages.append(Page(mims_portal_url(), "MIMS Portal", referrer=sls_login_url(), duration_s=rng.randint(30, 90)))
        mod = sls_module_url(rng)
        pages.append(Page(mod, "Learning Module - SLS", referrer=mims_portal_url(), duration_s=rng.randint(300, 900)))
    
    search_url = google_search_url(topic)
    pages.append(Page(search_url, google_search_title(topic), typed=True, duration_s=rng.randint(15, 45)))
    
    result_sites = [
        ("https://www.khanacademy.org/", "Khan Academy | Free Online Courses"),
        ("https://www.physicsclassroom.com/", "The Physics Classroom"),
        ("https://www.mathsisfun.com/", "Math is Fun"),
        ("https://brilliant.org/", "Brilliant | Learn to think"),
        ("https://www.chemguide.co.uk/", "chemguide"),
    ]
    
    for _ in range(rng.randint(2, 5)):
        site = rng.choice(result_sites)
        pages.append(Page(site[0], site[1], referrer=search_url, duration_s=rng.randint(120, 480)))
    
    if rng.random() < 0.75:
        yt_search = youtube_search_url(topic)
        pages.append(Page(yt_search, f"{topic} - YouTube", typed=False, referrer=search_url, duration_s=rng.randint(20, 60)))
        url, title = youtube_edu_video(rng)
        pages.append(Page(url, title, referrer=yt_search, duration_s=rng.randint(300, 900)))
    
    if rng.random() < 0.65:
        pages.append(Page("https://chat.openai.com/", "ChatGPT", typed=True, duration_s=rng.randint(180, 600)))
    
    return pages


def flow_revision_session(rng: random.Random) -> List[Page]:
    pages = []
    topic = pick_weighted(rng, build_academic_searches())
    
    if rng.random() < 0.55:
        url, title = quizlet_url(rng, topic.split()[0].title())
        pages.append(Page(url, title, typed=True, duration_s=rng.randint(300, 900)))
    
    if rng.random() < 0.45:
        url, title = notion_url(rng)
        pages.append(Page(url, title, typed=True, duration_s=rng.randint(300, 900)))
    
    search_url = google_search_url(topic)
    pages.append(Page(search_url, google_search_title(topic), typed=True, duration_s=rng.randint(20, 60)))
    
    edu_sites = [
        ("https://www.khanacademy.org/", "Khan Academy"),
        ("https://www.physicsclassroom.com/", "The Physics Classroom"),
        ("https://brilliant.org/", "Brilliant"),
    ]
    for _ in range(rng.randint(1, 3)):
        site = rng.choice(edu_sites)
        pages.append(Page(site[0], site[1], referrer=search_url, duration_s=rng.randint(180, 600)))
    

    
    if rng.random() < 0.6:
        url, title = youtube_edu_video(rng)
        pages.append(Page(url, title, typed=True, duration_s=rng.randint(300, 900)))
    
    if rng.random() < 0.55:
        pages.append(Page("https://chat.openai.com/", "ChatGPT", typed=True, duration_s=rng.randint(180, 600)))
    
    return pages if pages else [Page(search_url, google_search_title(topic), typed=True, duration_s=60)]


def flow_past_papers(rng: random.Random) -> List[Page]:
    pages = []
    topic = pick_weighted(rng, build_academic_searches())
    
    search_query = f"{topic.split()[0]} o level past year papers"
    search_url = google_search_url(search_query)
    pages.append(Page(search_url, google_search_title(search_query), typed=True, duration_s=rng.randint(20, 60)))
    
    url, title = exam_papers_url(rng)
    pages.append(Page(url, title, referrer=search_url, duration_s=rng.randint(300, 900)))
    
    doc = docs_url(rng, "document")
    pages.append(Page(doc, "Practice Answers - Google Docs", typed=True, duration_s=rng.randint(600, 1800)))
    
    if rng.random() < 0.6:
        pages.append(Page("https://chat.openai.com/", "ChatGPT", typed=True, duration_s=rng.randint(180, 600)))
    
    return pages


def flow_sls_learning(rng: random.Random) -> List[Page]:
    pages = []
    pages.append(Page(sls_login_url(), "SLS Login", typed=True, duration_s=rng.randint(15, 45)))
    pages.append(Page(mims_portal_url(), "MIMS Portal", referrer=sls_login_url(), duration_s=rng.randint(30, 90)))
    
    for _ in range(rng.randint(1, 3)):
        mod = sls_module_url(rng)
        pages.append(Page(mod, "Learning Module - SLS", referrer=mims_portal_url(), duration_s=rng.randint(300, 900)))
    
    return pages


def flow_classroom_work(rng: random.Random) -> List[Page]:
    pages = []
    pages.append(Page("https://classroom.google.com/u/0/h", "Google Classroom", typed=True, duration_s=rng.randint(30, 90)))
    
    course = classroom_course_url(rng)
    pages.append(Page(course, "Class - Google Classroom", referrer="https://classroom.google.com/u/0/h", duration_s=rng.randint(60, 180)))
    
    for _ in range(rng.randint(1, 3)):
        assign = classroom_assignment_url(rng, course)
        pages.append(Page(assign, "Assignment - Google Classroom", referrer=course, duration_s=rng.randint(60, 180)))
        if rng.random() < 0.7:
            doc = docs_url(rng, rng.choice(["document", "spreadsheets", "presentation"]))
            pages.append(Page(doc, "Assignment - Google Docs", referrer=assign, duration_s=rng.randint(300, 900)))
    
    return pages


def flow_quick_search(rng: random.Random) -> List[Page]:
    pages = []
    topic = pick_weighted(rng, build_academic_searches())
    
    search_url = google_search_url(topic)
    pages.append(Page(search_url, google_search_title(topic), typed=True, duration_s=rng.randint(15, 45)))
    
    sites = [
        ("https://www.khanacademy.org/", "Khan Academy"),
        ("https://www.mathsisfun.com/", "Math is Fun"),
        ("https://en.wikipedia.org/wiki/Main_Page", "Wikipedia"),
    ]
    
    for _ in range(rng.randint(1, 2)):
        site = rng.choice(sites)
        pages.append(Page(site[0], site[1], referrer=search_url, duration_s=rng.randint(60, 300)))
    
    return pages


# ============================================================================
# DAILY SCHEDULE
# ============================================================================

def make_daily_plan(rng: random.Random, day: dt.date) -> List[Tuple[int, str]]:
    weekday = day.weekday()
    is_weekend = weekday >= 5
    plan: List[Tuple[int, str]] = []

    if not is_weekend:
        if rng.random() < 0.45:
            plan.append((rng.randint(6*60+30, 7*60+45), "quick_search"))
        if rng.random() < 0.35:
            plan.append((rng.randint(10*60+15, 10*60+45), "quick_search"))
        if rng.random() < 0.40:
            plan.append((rng.randint(12*60+15, 13*60), "quick_search"))
        
        has_cca = rng.random() < 0.35
        if not has_cca:
            plan.append((rng.randint(14*60+30, 15*60+30), rng.choice(["homework", "classroom"])))
        
        if rng.random() < 0.75:
            plan.append((rng.randint(16*60+30, 18*60+30), rng.choice(["homework", "sls", "revision", "classroom"])))
        if rng.random() < 0.85:
            plan.append((rng.randint(19*60, 21*60), rng.choice(["revision", "homework", "past_papers"])))
        if rng.random() < 0.65:
            plan.append((rng.randint(21*60, 23*60), rng.choice(["revision", "past_papers", "homework"])))
        if rng.random() < 0.25:
            plan.append((rng.randint(23*60, 24*60+30), "revision"))
    else:
        plan.append((rng.randint(9*60, 11*60), rng.choice(["homework", "revision"])))
        if rng.random() < 0.7:
            plan.append((rng.randint(11*60, 13*60), rng.choice(["homework", "sls"])))
        if rng.random() < 0.8:
            plan.append((rng.randint(14*60, 16*60+30), rng.choice(["past_papers", "revision", "homework"])))
        if rng.random() < 0.65:
            plan.append((rng.randint(16*60+30, 18*60+30), rng.choice(["revision", "homework"])))
        plan.append((rng.randint(19*60, 21*60), rng.choice(["revision", "past_papers", "homework"])))
        if rng.random() < 0.75:
            plan.append((rng.randint(21*60, 23*60), rng.choice(["revision", "homework"])))

    plan.sort(key=lambda x: x[0])
    return plan


def generate_pages_for_session(rng: random.Random, session_type: str) -> List[Page]:
    if session_type == "homework":
        return flow_homework_session(rng)
    elif session_type == "revision":
        return flow_revision_session(rng)
    elif session_type == "past_papers":
        return flow_past_papers(rng)
    elif session_type == "sls":
        return flow_sls_learning(rng)
    elif session_type == "classroom":
        return flow_classroom_work(rng)
    elif session_type == "quick_search":
        return flow_quick_search(rng)
    else:
        return flow_quick_search(rng)


# ============================================================================
# HISTORY WRITER
# ============================================================================

class HistoryWriter:
    def __init__(self, con: sqlite3.Connection, rng: random.Random):
        self.con = con
        self.cur = con.cursor()
        self.rng = rng
        self._last_visit_time: Optional[int] = None

    def upsert_url(self, url: str, title: str, visit_time_chrome: int, typed: bool) -> int:
        row = self.cur.execute(
            "SELECT id, visit_count, typed_count, last_visit_time, COALESCE(title,'') FROM urls WHERE url=?",
            (url,),
        ).fetchone()

        if row is None:
            self.cur.execute(
                "INSERT INTO urls(url,title,visit_count,typed_count,last_visit_time,hidden) VALUES(?,?,?,?,?,0)",
                (url, title, 1, 1 if typed else 0, visit_time_chrome),
            )
            return int(self.cur.lastrowid)

        url_id, visit_count, typed_count, last_visit_time, existing_title = row
        final_title = existing_title if existing_title.strip() else title
        self.cur.execute(
            "UPDATE urls SET visit_count=?, typed_count=?, last_visit_time=?, title=? WHERE id=?",
            (int(visit_count) + 1, int(typed_count) + (1 if typed else 0), max(int(last_visit_time), visit_time_chrome), final_title, int(url_id)),
        )
        return int(url_id)

    def insert_visit(
        self,
        url_id: int,
        visit_time_chrome: int,
        from_visit: Optional[int],
        external_referrer_url: Optional[str],
        transition: int,
        duration_s: int,
        search_term: Optional[str] = None,
    ) -> int:
        self.cur.execute(
            """
            INSERT INTO visits(url, visit_time, from_visit, external_referrer_url, transition,
              visit_duration, incremented_omnibox_typed_score, is_known_to_sync,
              consider_for_ntp_most_visited, visited_link_id, app_id)
            VALUES(?,?,?,?,?, ?,0,0,0,0,NULL)
            """,
            (url_id, visit_time_chrome, from_visit, external_referrer_url, transition, int(duration_s * 1_000_000)),
        )
        visit_id = int(self.cur.lastrowid)
        self.cur.execute("INSERT OR IGNORE INTO visit_source(id, source) VALUES(?,?)", (visit_id, 0))
        
        self.cur.execute(
            """
            INSERT INTO content_annotations(visit_id, visibility_score, floc_protected_score, categories,
              page_topics_model_version, annotation_flags, entities, related_searches,
              search_normalized_url, search_terms, alternative_title, page_language, password_state, has_url_keyed_image)
            VALUES(?, -1, NULL, NULL, -1, 0, NULL, NULL, ?, ?, NULL, NULL, 0, 0)
            """,
            (visit_id, external_referrer_url if search_term else None, search_term),
        )
        
        duration_since_last = -1000000
        if self._last_visit_time is not None:
            duration_since_last = visit_time_chrome - self._last_visit_time
        
        window_id = self.rng.randint(1000000000, 2000000000)
        tab_id = window_id + 1
        task_id = visit_time_chrome
        
        self.cur.execute(
            """
            INSERT INTO context_annotations(visit_id, context_annotation_flags, duration_since_last_visit,
              page_end_reason, total_foreground_duration, browser_type,
              window_id, tab_id, task_id, root_task_id, parent_task_id, response_code)
            VALUES(?, 0, ?, ?, ?, 1, ?, ?, ?, ?, -1, 200)
            """,
            (visit_id, duration_since_last, self.rng.choice([3, 4, 5, 6]), int(duration_s * 1_000_000), window_id, tab_id, task_id, task_id),
        )
        
        self._last_visit_time = visit_time_chrome
        return visit_id

    def insert_search_term(self, url_id: int, term: str, keyword_id: int = 2) -> None:
        term = term.strip()
        if not term:
            return
        self.cur.execute(
            "INSERT INTO keyword_search_terms(keyword_id, url_id, term, normalized_term) VALUES(?,?,?,?)",
            (keyword_id, url_id, term, normalise_term(term)),
        )


def init_db(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(MIN_SCHEMA_SQL)
    con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('version','70')")
    con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('last_compatible_version','16')")
    con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('mmap_status','-1')")
    
    now_utc = dt.datetime.now(dt.timezone.utc)
    threshold_time = now_utc - dt.timedelta(days=90)
    threshold_chrome = to_chrome_time(threshold_time)
    con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('early_expiration_threshold',?)", (str(threshold_chrome),))
    con.commit()
    return con


def generate_history(writer: HistoryWriter, rng: random.Random, start_sg: dt.datetime, end_sg: dt.datetime) -> int:
    total_visits = 0
    day = start_sg.date()
    end_day = end_sg.date()

    while day <= end_day:
        session_plan = make_daily_plan(rng, day)
        for start_min, session_type in session_plan:
            t = dt.datetime.combine(day, dt.time(0, 0), tzinfo=start_sg.tzinfo) + dt.timedelta(minutes=start_min)
            if t < start_sg:
                t = start_sg
            if t > end_sg:
                continue

            pages = generate_pages_for_session(rng, session_type)
            prev_visit_id: Optional[int] = None
            prev_url: Optional[str] = None

            for i, p in enumerate(pages):
                if i > 0:
                    t += dt.timedelta(seconds=rng.randint(3, 40))
                if t > end_sg:
                    break

                chrome_t = to_chrome_time(t)
                url_id = writer.upsert_url(p.url, p.title, chrome_t, typed=p.typed)

                if p.typed:
                    transition = TRANSITION_TYPED_FROM_BAR
                else:
                    transition = TRANSITION_LINK
                
                from_visit = prev_visit_id if (not p.typed and prev_visit_id is not None) else None
                ext_ref = p.referrer if p.referrer else (prev_url if (not p.typed) else None)

                search_term = None
                if p.url.startswith("https://www.google.com/search?"):
                    parsed = urllib.parse.urlparse(p.url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    search_term = qs.get("q", [""])[0] or None

                visit_id = writer.insert_visit(
                    url_id=url_id,
                    visit_time_chrome=chrome_t,
                    from_visit=from_visit,
                    external_referrer_url=ext_ref,
                    transition=transition,
                    duration_s=clamp(p.duration_s, 5, 3600),
                    search_term=search_term,
                )
                total_visits += 1

                if search_term:
                    writer.insert_search_term(url_id, search_term, keyword_id=2)

                prev_visit_id = visit_id
                prev_url = p.url
                t += dt.timedelta(seconds=clamp(p.duration_s, 5, 3600))

        day += dt.timedelta(days=1)

    writer.con.commit()
    return total_visits


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {"message": "Chrome History Generator API", "docs": "/docs"}


@app.get("/api/generate")
async def generate_history_file(
    weeks: int = Query(default=3, ge=1, le=52, description="Number of weeks of history to generate"),
    seed: Optional[int] = Query(default=None, description="Random seed for reproducibility"),
):
    """Generate and download a Chrome History database file."""
    
    if seed is None:
        seed = random.randint(1, 999999)
    
    # Create temp file for SQLite database
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp_path = tmp.name
    
    try:
        con = init_db(tmp_path)
        rng = random.Random(seed)
        writer = HistoryWriter(con, rng)

        sg_tz = get_sg_tz()
        now_sg = dt.datetime.now(tz=sg_tz)
        start_sg = now_sg - dt.timedelta(days=weeks * 7)
        start_sg = start_sg.replace(hour=6, minute=rng.randint(10, 55), second=rng.randint(0, 59), microsecond=0)

        visits = generate_history(writer, rng, start_sg, now_sg)
        con.close()

        # Read the file into memory
        with open(tmp_path, "rb") as f:
            content = f.read()
        
        # Return as downloadable file
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename=History",
                "X-Seed": str(seed),
                "X-Weeks": str(weeks),
                "X-Visits": str(visits),
            }
        )
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.get("/api/preview")
async def preview_history(
    weeks: int = Query(default=1, ge=1, le=4, description="Number of weeks to preview"),
    seed: Optional[int] = Query(default=None, description="Random seed"),
    limit: int = Query(default=50, ge=1, le=200, description="Number of entries to return"),
):
    """Preview generated history without downloading."""
    
    if seed is None:
        seed = random.randint(1, 999999)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp_path = tmp.name
    
    try:
        con = init_db(tmp_path)
        rng = random.Random(seed)
        writer = HistoryWriter(con, rng)

        sg_tz = get_sg_tz()
        now_sg = dt.datetime.now(tz=sg_tz)
        start_sg = now_sg - dt.timedelta(days=weeks * 7)
        start_sg = start_sg.replace(hour=6, minute=rng.randint(10, 55), second=rng.randint(0, 59), microsecond=0)

        visits = generate_history(writer, rng, start_sg, now_sg)
        
        # Query recent entries
        cur = con.cursor()
        rows = cur.execute("""
            SELECT 
                datetime(v.visit_time/1000000-11644473600, 'unixepoch', 'localtime') as time,
                u.url,
                u.title
            FROM visits v 
            JOIN urls u ON v.url = u.id 
            ORDER BY v.visit_time DESC 
            LIMIT ?
        """, (limit,)).fetchall()
        
        con.close()
        
        return {
            "seed": seed,
            "weeks": weeks,
            "total_visits": visits,
            "preview": [{"time": r[0], "url": r[1], "title": r[2]} for r in rows]
        }
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
