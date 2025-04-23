import os
import sys
import psycopg2
import hashlib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import google.generativeai as genai
from tavily import TavilyClient
from newsapi import search_newsapi
from searchweb import search_web_tavily
from fetchresponse import fetch_tweets_requests, fetch_reddit_claims_for_llm
from LLM import evaluate_claim_with_llm
from DB import get_db_connection, store_verification_data
import time

load_dotenv()

# Database (Supabase Pooler details)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "6543")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

TEST_BEARER_TOKEN = os.getenv("TEST_BEARER_TOKEN") # <--- Get Bearer Token
print(f"DEBUG: Loaded TEST_BEARER_TOKEN = {TEST_BEARER_TOKEN}") # <-- ADD THIS LINE

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # <--- Get Tavily Key

LLM_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")

if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, TEST_BEARER_TOKEN, TAVILY_API_KEY, LLM_API_KEY, NEWSAPI_KEY]):
    print("ERROR: Missing essential configuration in .env file (DB, X, Tavily, LLM). Exiting.")
    sys.exit(1)


    
try:
    genai.configure(api_key=LLM_API_KEY)
    llm_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    print("Google Gemini model initialized.")
except Exception as e:
    print(f"ERROR: Failed to initialize Google Gemini model: {e}")
    sys.exit(1)
    

# --- Main Execution Logic ---
if __name__ == "__main__":
    print("Starting Claim Verification Process...")
    db_conn = get_db_connection(DB_HOST=DB_HOST, DB_PORT=DB_PORT, DB_NAME=DB_NAME, DB_USER=DB_USER, DB_PASSWORD=DB_PASSWORD) # Get DB connection here

    RELIABLE_SVENSKA_POLITIK_DOMAINS = [
        # Swedish News & Government
        "svt.se",
        "sr.se",
        "dn.se",
        "svd.se",
        "riksdagen.se",
        "regeringen.se",
        "scb.se",
        "faktiskt.se",
        "tillvaxtverket.se",
        "msb.se",
        "folkhalsomyndigheten.se",

        # International News & Fact-Checking
        "apnews.com",
        "reuters.com",
        "bbc.com",
        "nytimes.com",
        "theguardian.com",
        "politifact.com",
        "factcheck.org",
        "snopes.com",
        "fullfact.org",

        # Scientific and Academic Sources
        "nature.com",
        "sciencemag.org",
        "nejm.org",
        "thelancet.com",
        "pubmed.ncbi.nlm.nih.gov",
        "who.int",
        "ecdc.europa.eu",
        "un.org",
        "europa.eu"
    ]


    twitter_search_query = '#svpol'
    max_tweets_to_fetch = 1

    # --- Fetch Tweets using Requests function ---
    tweets = fetch_tweets_requests(twitter_search_query, max_tweets_to_fetch, TEST_BEARER_TOKEN)
    reddit_posts = fetch_reddit_claims_for_llm(max_tweets_to_fetch, client_id=os.getenv("REDDIT_CLIENT_ID"), client_secret=os.getenv("REDDIT_CLIENT_SECRET"), user_agent="python:desinformation-agent:v0.0.1 (by u/laughingmaymays)", subreddit="svenskpolitik")

    # --- Process the single fetched tweet ---
    if not tweets and not reddit_posts:
        print("No tweets or Reddit posts fetched matching the criteria.")
        print("No tweet fetched matching the criteria.")
        if db_conn:
            db_conn.close()
        sys.exit(0)


    for tweet in tweets:
        # Process tweet
        print(f"Processing tweet: {tweet['id']}")
        claim_text = tweet['text']
        
        # Search for evidence
        search_query = claim_text.split('#', 1)[0].strip()
        tavily_results = search_web_tavily(search_query, max_results=5, include_domains=RELIABLE_SVENSKA_POLITIK_DOMAINS, tavily_key=TAVILY_API_KEY)

        time.sleep(1)
        newsapi_results = search_newsapi(search_query, max_results=5, language='sv', NEWSAPI_KEY=NEWSAPI_KEY)

        time.sleep(1)
        search_results = tavily_results + newsapi_results
        
        # Evaluate claim
        evaluation = evaluate_claim_with_llm(claim_text, search_results, llm_model=llm_model)
        
        # Prepare data for storage
        source_data = {
            'platform': 'Twitter/X',
            'source_url': tweet['source_url'],
            'author_id': tweet.get('author_id'),
            'author_username': tweet.get('author_username'),
            'post_timestamp': datetime.strptime(tweet['created_at'], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc) if tweet.get('created_at') else None,
            'fetch_timestamp': datetime.now(timezone.utc)
        }
        
        claim_data = {
            'claim_text': claim_text,
            'extraction_method': 'full_tweet_text',
            'date_extracted': datetime.now(timezone.utc)
        }
        
        evaluation_data = {
            'evaluation_timestamp': datetime.now(timezone.utc),
            'llm_model_used': GEMINI_MODEL_NAME,
            'search_api_used': 'tavily_search_api',
            'search_query_used': search_query,
            'truthfulness_rating': evaluation['rating'],
            'truthfulness_score': evaluation.get('truthfulness_score'),
            'llm_reasoning': evaluation['reasoning'],
            'evaluation_status': 'Completed'
        }
        
        # Store data in database
        store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results, GEMINI_MODEL_NAME)

    # --- Cleanup ---
    if db_conn:
        db_conn.close()
        print("Database connection closed.")

    print("Claim Verification Process Finished.")