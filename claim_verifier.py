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
import random
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

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # <--- Get Tavily Key

LLM_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")

# Commenting out Twitter token requirement since we're only using Reddit
if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, TAVILY_API_KEY, LLM_API_KEY, NEWSAPI_KEY]):
    print("ERROR: Missing essential configuration in .env file (DB, Tavily, LLM). Exiting.")
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

    # Comment out Twitter variables since we're not using them
    # twitter_search_query = '#svpol'
    # max_tweets_to_fetch = 1
    
    # Increase the number of Reddit posts to fetch
    max_posts_to_fetch = 10  # Increased from 3 to 10
    max_days_reddit = 5      # Increased from 2 to 5 days to get more posts

    # --- Comment out Twitter fetching, only fetch Reddit posts ---
    # tweets = fetch_tweets_requests(twitter_search_query, max_tweets_to_fetch, TEST_BEARER_TOKEN)
    
    print(f"Fetching up to {max_posts_to_fetch} Reddit posts from the last {max_days_reddit} days...")
    reddit_posts = fetch_reddit_claims_for_llm(
        max_results=max_posts_to_fetch, 
        client_id=os.getenv("REDDIT_CLIENT_ID"), 
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"), 
        user_agent="python:desinformation-agent:v0.0.1 (by u/laughingmaymays)", 
        subreddit="svenskpolitik",
        max_days=max_days_reddit  # Limit to posts from the last 2 days
    )

    # --- Check only for Reddit posts ---
    if not reddit_posts:
        print("No Reddit posts fetched matching the criteria.")
        if db_conn:
            db_conn.close()
        sys.exit(0)
    else:
        print(f"Successfully fetched {len(reddit_posts)} Reddit posts for processing.")

    # --- Comment out Twitter processing ---
    '''
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
    '''

    # Process Reddit posts with linked articles as claims
    processed_count = 0
    for post in reddit_posts:
        print(f"\n=== Processing Reddit post {processed_count + 1}/{len(reddit_posts)}: {post['url']} ===")
        
        # Check if the post has a linked article
        if 'link_content' in post and post['link_content']:
            # Use the article content as the claim source instead of Reddit post title
            article_title = post.get('link_title', 'Unknown Article')
            article_url = post.get('link_url', '')
            article_domain = post.get('link_domain', '')
            
            print(f"Processing linked article: {article_title} from {article_domain}")
            
            # Extract claims from article content using LangChain chunks
            if 'link_chunks' in post and post['link_chunks']:
                article_chunks = post['link_chunks']
            else:
                # If no chunks, use the main content
                article_chunks = [post['link_content']]
            
            # Process each chunk of the article as a separate claim
            for chunk_index, chunk_content in enumerate(article_chunks):
                # Limit chunk size for processing
                claim_text = chunk_content[:2000] if len(chunk_content) > 2000 else chunk_content
                
                if not claim_text.strip():
                    print(f"Skipping empty chunk {chunk_index}")
                    continue
                    
                print(f"Processing article chunk {chunk_index+1}/{len(article_chunks)}")
                
                # Search for evidence
                # Use the article title + first sentence as the search query for better results
                first_sentence = claim_text.split('.')[0] if '.' in claim_text else claim_text[:100]
                search_query = f"{article_title}: {first_sentence}".strip()
                
                # Limit search query length
                if len(search_query) > 200:
                    search_query = search_query[:200]
                    
                print(f"Using search query: {search_query}")
                
                tavily_results = search_web_tavily(search_query, max_results=5, include_domains=RELIABLE_SVENSKA_POLITIK_DOMAINS, tavily_key=TAVILY_API_KEY)
                time.sleep(1)
                
                newsapi_results = search_newsapi(search_query, max_results=5, language='sv', NEWSAPI_KEY=NEWSAPI_KEY)
                time.sleep(1)
                
                # Create the evidence list, excluding the source article itself to avoid circular reasoning
                search_results = []
                for result in tavily_results + newsapi_results:
                    # Skip if this is the same article we're analyzing
                    if result.get('url') == article_url:
                        continue
                    search_results.append(result)
                
                # Remove Reddit post as context evidence - only use the linked article content as the claim
                # and external evidence for evaluation
                
                # Evaluate claim
                evaluation = evaluate_claim_with_llm(claim_text, search_results, llm_model=llm_model)
                
                # Prepare data for storage
                source_data = {
                    'platform': f"Article via Reddit",
                    'source_url': article_url,
                    'author_id': post.get('author', 'unknown'),  # Reddit user who shared it
                    'author_username': post.get('author', 'unknown'),
                    'post_timestamp': datetime.fromisoformat(post['created_at']) if 'created_at' in post else datetime.now(timezone.utc),
                    'fetch_timestamp': datetime.now(timezone.utc)
                }
                
                claim_data = {
                    'claim_text': claim_text,
                    'extraction_method': f'linked_article_content_chunk_{chunk_index+1}',
                    'date_extracted': datetime.now(timezone.utc)
                }
                
                # Include information about the evidence sources in the evaluation data
                evidence_sources = "article_via_reddit,tavily_search_api,newsapi"
                
                evaluation_data = {
                    'evaluation_timestamp': datetime.now(timezone.utc),
                    'llm_model_used': GEMINI_MODEL_NAME,
                    'search_api_used': evidence_sources,
                    'search_query_used': search_query,
                    'truthfulness_rating': evaluation['rating'],
                    'truthfulness_score': evaluation.get('truthfulness_score'),
                    'llm_reasoning': evaluation['reasoning'],
                    'evaluation_status': 'Completed'
                }
                
                # Store data in database
                store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results, GEMINI_MODEL_NAME)
                
                # Add a small delay between processing chunks
                time.sleep(2)
                
        else:
            # Process the Reddit post itself as a claim if it has no linked article
            print(f"Processing Reddit post as claim (no article link): {post['title']}")
            
            # Combine title and post content for a more complete claim
            post_title = post.get('title', '')
            post_content = post.get('snippet', '')
            
            # Use both title and content if available, or just title
            if post_content and len(post_content) > 10:  # Ensure there's meaningful content
                claim_text = f"{post_title}\n\n{post_content}"
            else:
                claim_text = post_title
                
            # Limit claim size for processing
            claim_text = claim_text[:2000] if len(claim_text) > 2000 else claim_text
            
            # Skip if there's no meaningful claim
            if not claim_text.strip():
                print(f"Skipping empty Reddit post: {post['url']}")
                continue
                
            # Search for evidence
            search_query = post_title.strip()
            
            # Limit search query length
            if len(search_query) > 200:
                search_query = search_query[:200]
                
            print(f"Using search query: {search_query}")
            
            tavily_results = search_web_tavily(search_query, max_results=5, include_domains=RELIABLE_SVENSKA_POLITIK_DOMAINS, tavily_key=TAVILY_API_KEY)
            time.sleep(1)
            
            newsapi_results = search_newsapi(search_query, max_results=5, language='sv', NEWSAPI_KEY=NEWSAPI_KEY)
            time.sleep(1)
            
            # Combine search results
            search_results = tavily_results + newsapi_results
            
            # Evaluate claim
            evaluation = evaluate_claim_with_llm(claim_text, search_results, llm_model=llm_model)
            
            # Prepare data for storage
            source_data = {
                'platform': 'Reddit',
                'source_url': post['url'],
                'author_id': post.get('author', 'unknown'),
                'author_username': post.get('author', 'unknown'),
                'post_timestamp': datetime.fromisoformat(post['created_at']) if 'created_at' in post else datetime.now(timezone.utc),
                'fetch_timestamp': datetime.now(timezone.utc)
            }
            
            claim_data = {
                'claim_text': claim_text,
                'extraction_method': 'reddit_post_content',
                'date_extracted': datetime.now(timezone.utc)
            }
            
            evidence_sources = "reddit_post,tavily_search_api,newsapi"
            
            evaluation_data = {
                'evaluation_timestamp': datetime.now(timezone.utc),
                'llm_model_used': GEMINI_MODEL_NAME,
                'search_api_used': evidence_sources,
                'search_query_used': search_query,
                'truthfulness_rating': evaluation['rating'],
                'truthfulness_score': evaluation.get('truthfulness_score'),
                'llm_reasoning': evaluation['reasoning'],
                'evaluation_status': 'Completed'
            }
            
            # Store data in database
            store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results, GEMINI_MODEL_NAME)

        processed_count += 1

    print(f"\nProcessed a total of {processed_count} Reddit posts.")
    
    # --- Cleanup ---
    if db_conn:
        db_conn.close()
        print("Database connection closed.")

    print("Claim Verification Process Finished.")