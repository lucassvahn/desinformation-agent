import os
import sys
import argparse
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

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Verify claims from Reddit, Twitter, or manually entered claims.')
parser.add_argument('--claim', type=str, help='Manually enter a claim to verify')
parser.add_argument('--skip-reddit', action='store_true', help='Skip fetching from Reddit')
parser.add_argument('--skip-twitter', action='store_true', help='Skip fetching from Twitter')
parser.add_argument('--source-url', type=str, help='Source URL for manually entered claim')
parser.add_argument('--author', type=str, default='manual_input', help='Author for manually entered claim')
args = parser.parse_args()

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


    twitter_search_query = '#svpol'

    subreddits_to_scan = ["svenskpolitik", "Sverige", "sweden"]
    
    max_posts_per_subreddit = 20
    max_days_reddit = 7    

    # Process manually entered claim if provided
    if args.claim:
        print("\n=== Processing manually entered claim ===")
        claim_text = args.claim
        source_url = args.source_url if args.source_url else 'manual_input'
        author = args.author

        # Search for evidence
        search_query = claim_text.split('#', 1)[0].strip()
        tavily_results = search_web_tavily(search_query, max_results=5, include_domains=RELIABLE_SVENSKA_POLITIK_DOMAINS, tavily_key=TAVILY_API_KEY)
        time.sleep(1)
        newsapi_results = search_newsapi(search_query, max_results=5, language='sv', NEWSAPI_KEY=NEWSAPI_KEY)
        time.sleep(1)
        search_results = tavily_results + newsapi_results

        # Evaluate claim
        evaluation = evaluate_claim_with_llm(
            claim_text, search_results, llm_model=llm_model,
            metadata={
                'platform': 'Manual Input',
                'post_date': datetime.now(timezone.utc).isoformat()
            }
        )

        # Prepare data for storage
        source_data = {
            'platform': 'Manual Input',
            'source_url': source_url,
            'author_id': author,
            'author_username': author,
            'post_timestamp': datetime.now(timezone.utc),
            'fetch_timestamp': datetime.now(timezone.utc)
        }

        claim_data = {
            'claim_text': claim_text,
            'extraction_method': 'manual_input',
            'date_extracted': datetime.now(timezone.utc)
        }

        evaluation_data = {
            'evaluation_timestamp': datetime.now(timezone.utc),
            'llm_model_used': GEMINI_MODEL_NAME,
            'search_api_used': 'tavily_search_api,newsapi',
            'search_query_used': search_query,
            'truthfulness_rating': evaluation['rating'],
            'truthfulness_score': evaluation.get('truthfulness_score'),
            'llm_reasoning': evaluation['reasoning'],
            'claims_detected': evaluation.get('claims_detected'),
            'evaluation_status': 'Completed'
        }

        # Store data in database
        store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results, GEMINI_MODEL_NAME)
        
        # Close the database connection and exit
        if db_conn:
            db_conn.close()
            print("Database connection closed.")
        
        print("Manual claim verification completed.")
        sys.exit(0)  # Exit after processing manual claim
    
    # We'll store all fetched posts here
    all_reddit_posts = []
    
    # Fetch posts from each subreddit, but ONLY if not skipped and no manual claim was provided
    if not args.skip_reddit:
        for subreddit in subreddits_to_scan:
            print(f"\n=== Fetching posts from r/{subreddit} ===")
            reddit_posts = fetch_reddit_claims_for_llm(
                max_results=max_posts_per_subreddit, 
                client_id=os.getenv("REDDIT_CLIENT_ID"), 
                client_secret=os.getenv("REDDIT_CLIENT_SECRET"), 
                subreddit=subreddit,
                max_days=max_days_reddit,
                extract_links=False  # Skip article content extraction, use Reddit post titles instead
            )
                
            if reddit_posts:
                print(f"Successfully fetched {len(reddit_posts)} posts from r/{subreddit}")
                all_reddit_posts.extend(reddit_posts)
            else:
                print(f"No posts fetched from r/{subreddit}")
    else:
        print("Reddit fetching skipped based on command-line argument.")
    
    # --- Check if we got any Reddit posts ---
    if not all_reddit_posts and not args.claim:
        print("No Reddit posts fetched from any subreddit and no manual claim provided. Exiting.")
        if db_conn:
            db_conn.close()
        sys.exit(0)
    else:
        print(f"Successfully fetched a total of {len(all_reddit_posts)} Reddit posts for processing.")

    # --- Configure Twitter search ---
    twitter_search_query = '#svpol'
    max_tweets_to_fetch = 10
    
    # Fetch tweets if not skipped via command-line argument
    tweets = []
    if not args.skip_twitter and TEST_BEARER_TOKEN:
        print(f"\n=== Fetching tweets with search query: {twitter_search_query} ===")
        tweets = fetch_tweets_requests(twitter_search_query, max_tweets_to_fetch, TEST_BEARER_TOKEN)
        if tweets:
            print(f"Successfully fetched {len(tweets)} tweets.")
        else:
            print("No tweets fetched. Continuing with Reddit posts only.")
    else:
        if args.skip_twitter:
            print("Twitter fetching skipped based on command-line argument.")
        elif not TEST_BEARER_TOKEN:
            print("Twitter API token not found. Skipping Twitter fetching.")

    # --- Check only for Reddit posts ---
    if not all_reddit_posts and not args.claim:
        print("No Reddit posts fetched matching the criteria and no manual claim provided.")
        if db_conn:
            db_conn.close()
        sys.exit(0)
    else:
        print(f"Successfully fetched {len(all_reddit_posts)} Reddit posts for processing.")

    # --- Process Reddit posts with linked articles as claims ---
    processed_count = 0
    for post in all_reddit_posts:
        print(f"\n=== Processing Reddit post {processed_count + 1}/{len(all_reddit_posts)}: {post['url']} ===")
        
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
                evaluation = evaluate_claim_with_llm(
                    claim_text, search_results, llm_model=llm_model,
                    metadata={
                        'platform': source_data['platform'],
                        'post_date': source_data['post_timestamp'].isoformat() if 'post_timestamp' in source_data else None
                    }
                )
                
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
                
            source_data = {
                'platform': 'Reddit',
                'source_url': post['url'],
                'author_id': post.get('author', 'unknown'),
                'author_username': post.get('author', 'unknown'),
                'post_timestamp': datetime.fromisoformat(post['created_at']) if 'created_at' in post else datetime.now(timezone.utc),
                'fetch_timestamp': datetime.now(timezone.utc)
            }
            
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
            evaluation = evaluate_claim_with_llm(
                claim_text, search_results, llm_model=llm_model,
                metadata={
                    'platform': source_data['platform'],
                    'post_date': source_data['post_timestamp'].isoformat() if 'post_timestamp' in source_data else None
                }
            )
            
            
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

    # --- Process Twitter posts as claims ---
    if tweets:
        print("\n=== Processing Twitter/X posts ===")
        for i, tweet in enumerate(tweets):
            print(f"\nProcessing Twitter post {i + 1}/{len(tweets)}: {tweet['source_url']}")
            
            claim_text = tweet.get('text', '')
            
            # Skip if there's no meaningful content
            if not claim_text.strip():
                print(f"Skipping empty Twitter post: {tweet['source_url']}")
                continue
                
            # Limit claim size for processing
            claim_text = claim_text[:2000] if len(claim_text) > 2000 else claim_text
            
            # Search for evidence
            search_query = claim_text.split('#', 1)[0].strip()  # Remove hashtags for searching
            
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

                        # Prepare data for storage
            source_data = {
                'platform': 'Twitter/X',
                'source_url': tweet['source_url'],
                'author_id': tweet.get('author_id', 'unknown'),
                'author_username': tweet.get('author_username', 'unknown'),
                'post_timestamp': datetime.fromisoformat(tweet['created_at']) if 'created_at' in tweet else datetime.now(timezone.utc),
                'fetch_timestamp': datetime.now(timezone.utc)
            }
            
            # Evaluate claim
            evaluation = evaluate_claim_with_llm(
                claim_text, search_results, llm_model=llm_model,
                metadata={
                    'platform': source_data['platform'],
                    'post_date': source_data['post_timestamp'].isoformat() if 'post_timestamp' in source_data else None
                }
            )
            

            
            claim_data = {
                'claim_text': claim_text,
                'extraction_method': 'twitter_post_content',
                'date_extracted': datetime.now(timezone.utc)
            }
            
            evidence_sources = "twitter_post,tavily_search_api,newsapi"
            
            evaluation_data = {
                'evaluation_timestamp': datetime.now(timezone.utc),
                'llm_model_used': GEMINI_MODEL_NAME,
                'search_api_used': evidence_sources,
                'search_query_used': search_query,
                'truthfulness_rating': evaluation['rating'],
                'truthfulness_score': evaluation.get('truthfulness_score'),
                'llm_reasoning': evaluation['reasoning'],
                'claims_detected': evaluation.get('claims_detected'),
                'evaluation_status': 'Completed'
            }
            
            # Store data in database
            store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results, GEMINI_MODEL_NAME)

    # --- Cleanup ---
    if db_conn:
        db_conn.close()
        print("Database connection closed.")

    print("Claim Verification Process Finished.")