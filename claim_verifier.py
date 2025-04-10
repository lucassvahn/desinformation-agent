import os
import sys
import psycopg2
import requests
# requests is still useful for potential future basic HTTP calls, keep it for now
# import requests
import json
import time
import hashlib
from datetime import datetime, timezone
from dotenv import load_dotenv
import google.generativeai as genai
from tavily import TavilyClient # <--- Import TavilyClient

# --- Configuration Loading ---
load_dotenv()

# Database (Supabase Pooler details)
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "6543") # Default to pooler port
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

TEST_BEARER_TOKEN = os.getenv("TEST_BEARER_TOKEN") # <--- Get Bearer Token
print(f"DEBUG: Loaded TEST_BEARER_TOKEN = {TEST_BEARER_TOKEN}") # <-- ADD THIS LINE

# Tavily API Key
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # <--- Get Tavily Key

# Google Gemini LLM API Key (assuming it's the same GOOGLE_API_KEY)
LLM_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash")

# Basic checks for essential configuration
# Updated checks
if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, TEST_BEARER_TOKEN, TAVILY_API_KEY, LLM_API_KEY]):
    print("ERROR: Missing essential configuration in .env file (DB, X, Tavily, LLM). Exiting.")
    sys.exit(1)

# --- API Clients Setup ---



try:
    tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    print("Tavily Search Client initialized.")
except Exception as e:
    print(f"ERROR: Failed to initialize Tavily client: {e}")
    sys.exit(1)
    

# Google Gemini LLM (No changes needed here if still using Gemini)

try:
    genai.configure(api_key=LLM_API_KEY)
    llm_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    print("Google Gemini model initialized.")
except Exception as e:
    print(f"ERROR: Failed to initialize Google Gemini model: {e}")
    sys.exit(1)
    

# Twitter/X API Client (No changes needed here)


# --- Database Connection ---
# (No changes needed in get_db_connection function)
def get_db_connection():
    """Establishes connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        print("Database connection successful.")
        return conn
    except psycopg2.Error as e:
        print(f"ERROR: Unable to connect to the database: {e}")
        sys.exit(1)

# --- Core Functions ---

# (No changes needed in fetch_tweets function)
def fetch_tweets_requests(query, max_results=1):
    """Fetches recent tweets matching the query using X API v2 and the Requests library."""
    print(f"Fetching up to {max_results} tweets via Requests for query: '{query}'")
    tweets_data = []
    search_url = "https://api.twitter.com/2/tweets/search/recent"

    bearer_token = os.getenv("TEST_BEARER_TOKEN")
    if not bearer_token:
        print("ERROR: Bearer token not found in environment variables.")
        return []

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "v2RecentSearchPython"
    }

    full_query = f"{query} -is:retweet -is:reply lang:sv"
    actual_max_results = max(10, min(100, max_results))
    params = {
        'query': full_query,
        'max_results': actual_max_results,
        'tweet.fields': 'created_at,author_id'
    }

    print(f"Requesting URL: {search_url} with query: '{full_query}'")

    try:
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        json_response = response.json()

        author_username = 'unknown'

        if 'data' in json_response and json_response['data']:
            print(f"Found {len(json_response['data'])} tweets.")
            for tweet in json_response['data']:
                author_id = tweet.get('author_id')
                source_url = f"https://x.com/{author_username}/status/{tweet['id']}"

                tweets_data.append({
                    "id": tweet.get('id'),
                    "text": tweet.get('text'),
                    "author_id": author_id,
                    "author_username": author_username,
                    "created_at": tweet.get('created_at'),
                    "source_url": source_url
                })
        elif 'meta' in json_response and json_response['meta'].get('result_count', 0) == 0:
            print("No tweets found matching the query.")
        else:
            print(f"WARNING: Unexpected response format: {json_response}")
            return []
    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error occurred during tweet fetching: {http_err}")
        print(f"Response status code: {http_err.response.status_code}")
        try:
            print(f"Response body: {http_err.response.text}")
        except:
            print("Could not decode error response body.")
        return []
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Failed to fetch tweets due to RequestException: {req_err}")
        return []
    except json.JSONDecodeError as json_err:
        print(f"ERROR: Failed to decode JSON response from X API: {json_err}")
        print(f"Response text: {response.text if 'response' in locals() else 'N/A'}")
        return []
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        return []

    return tweets_data

# --- Updated Search Function ---
def search_web_tavily(query, max_results=5):
    """Performs a Tavily Search for the query."""
    # Note: Tavily might not have explicit Swedish language *filtering* like Google's 'lr=lang_sv'.
    # It searches broadly. Results quality depends on the Swedish query terms and Tavily's index.
    print(f"Searching web (Tavily) for: '{query}'")
    results = []
    try:
        # Use tavily_client.search method
        # search_depth can be 'basic' or 'advanced'. 'basic' is often sufficient.
        response = tavily_client.search(
            query=query,
            search_depth="basic",
            max_results=max_results
            # include_domains=[], # Optional: restrict to specific domains
            # exclude_domains=[] # Optional: exclude specific domains
            )

        # Parse the response (structure is typically {'results': [...]})
        if 'results' in response and response['results']:
            for item in response['results']:
                results.append({
                    'title': item.get('title'),
                    'url': item.get('url'),
                    'snippet': item.get('content') # Tavily often calls the snippet 'content'
                })
            print(f"Found {len(results)} search results via Tavily.")
        else:
            print("No search results found via Tavily.")

    except Exception as e:
        print(f"ERROR: Tavily Search API call failed: {e}")

    return results

# (No changes needed in evaluate_claim_with_llm function, it just consumes the search results)
def evaluate_claim_with_llm(claim_text, search_results):
    """Uses Google Gemini to evaluate the claim based on search results."""
    print(f"Evaluating claim using LLM: '{claim_text.split('#', 1)[0].strip()}...'")
    if not search_results:
        print("WARNING: No search results provided to LLM. Evaluation may be unreliable.")
        return {"rating": "Cannot Verify", "reasoning": "No search results available to verify the claim."}
    prompt = f"""
    Please act as a neutral fact-checker. Evaluate the truthfulness of the following claim based on the provided search results snippets. The original claim and search results may be in Swedish. Your output should also be in swedish.
    If you have access to external information or knowledge, you are allowed to use this, as long as you stay unbiased.

    Claim:
    "{claim_text}"

    Search Results Snippets:
    """
    for i, result in enumerate(search_results, 1):
        prompt += f"\n{i}. URL: {result.get('url', 'N/A')}\n   Title: {result.get('title', 'N/A')}\n   Snippet: {result.get('snippet', 'N/A')}\n"
    prompt += """
    Based on these snippets, provide:
    1.  A truthfulness rating from the following categories:
        * Likely True
        * Likely False
        * Misleading
        * Uncertain
        * Cannot Verify
    2.  A brief reasoning (1-2 sentences) explaining your rating.
    3.  A numeric "Truthfulness Score" from 0 to 10.

    Output format should be:
    Rating: [Your chosen rating category]
    Reasoning: [Your brief explanation]
    Truthfulness Score: [0-10]
    """
    try:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = llm_model.generate_content(prompt, safety_settings=safety_settings)
        llm_output = response.text.strip()
        print(f"LLM Raw Output:\n{llm_output}")

        rating = "Error Parsing LLM Output"
        reasoning = "Could not parse the reasoning from the LLM response."
        truthfulness_score = None

        lines = llm_output.split('\n')
        for line in lines:
            if line.lower().startswith("rating:"):
                rating = line.split(":", 1)[1].strip()
            elif line.lower().startswith("reasoning:"):
                reasoning = line.split(":", 1)[1].strip()
            elif line.lower().startswith("truthfulness score:"):
                truthfulness_score = line.split(":", 1)[1].strip()

        valid_ratings = ['Likely True', 'Likely False', 'Misleading', 'Uncertain', 'Cannot Verify', 'Error Parsing LLM Output']
        if rating not in valid_ratings:
             print(f"WARNING: LLM provided an unexpected rating category: {rating}. Storing as is.")

        print(f"Parsed Rating: {rating}")
        print(f"Parsed Reasoning: {reasoning}")
        print(f"Parsed Truthfulness Score: {truthfulness_score}")

        return {"rating": rating, "reasoning": reasoning, "truthfulness_score": truthfulness_score}
    except Exception as e:
        print(f"ERROR: LLM API call or parsing failed: {e}")
        try:
            print(f"LLM Prompt Feedback: {response.prompt_feedback}")
        except:
            pass
        return {"rating": "LLM Error", "reasoning": f"An error occurred during LLM evaluation: {e}", "truthfulness_score": None}

# (No changes needed in store_verification_data function structure, only update search_api_used string)
def store_verification_data(conn, source_data, claim_data, evaluation_data, evidence_list):
    """Stores all collected data into the database using a transaction."""
    cursor = None
    try:
        cursor = conn.cursor()
        print(f"Storing data for source URL: {source_data['source_url']}")
        # 1. Check/Insert Source
        cursor.execute("SELECT source_id FROM Sources WHERE source_url = %s", (source_data['source_url'],))
        existing_source = cursor.fetchone()
        if existing_source:
            source_id = existing_source[0]
            print(f"Source already exists with ID: {source_id}. Skipping Source insertion.")
        else:
            print("Inserting new source...")
            sql_source = """
                INSERT INTO Sources (platform, source_url, author_id, author_username, post_timestamp, fetch_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING source_id;
            """
            cursor.execute(sql_source, (
                source_data['platform'], source_data['source_url'], source_data.get('author_id'),
                source_data.get('author_username'), source_data.get('post_timestamp'), source_data['fetch_timestamp']
            ))
            source_id = cursor.fetchone()[0]
            print(f"New Source inserted with ID: {source_id}")
        # 2. Insert Claim
        print("Inserting claim...")
        sql_claim = """
            INSERT INTO Claims (source_id, claim_text, claim_hash, extraction_method, date_extracted)
            VALUES (%s, %s, %s, %s, %s) RETURNING claim_id;
        """
        claim_hash = hashlib.sha256(claim_data['claim_text'].encode()).hexdigest()
        cursor.execute(sql_claim, (
            source_id, claim_data['claim_text'], claim_hash,
            claim_data.get('extraction_method', 'full_tweet_text'), claim_data['date_extracted']
        ))
        claim_id = cursor.fetchone()[0]
        print(f"Claim inserted with ID: {claim_id}")
        # 3. Insert Evaluation
        print("Inserting evaluation...")
        sql_evaluation = """
            INSERT INTO Evaluations (claim_id, evaluation_timestamp, llm_model_used, search_api_used,
                                     search_query_used, truthfulness_rating, truthfulness_score,
                                     llm_reasoning, evaluation_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING evaluation_id;
        """
        cursor.execute(sql_evaluation, (
            claim_id, evaluation_data['evaluation_timestamp'], evaluation_data.get('llm_model_used', GEMINI_MODEL_NAME),
            # --- Update the search_api_used string ---
            evaluation_data.get('search_api_used', 'tavily_search_api'), # <--- UPDATED
            evaluation_data.get('search_query_used'), evaluation_data['truthfulness_rating'],
            evaluation_data.get('truthfulness_score'), evaluation_data['llm_reasoning'],
            evaluation_data.get('evaluation_status', 'Completed')
        ))
        evaluation_id = cursor.fetchone()[0]
        print(f"Evaluation inserted with ID: {evaluation_id}")
        # 4. Insert Evidence
        print(f"Inserting {len(evidence_list)} evidence items...")
        sql_evidence = """
            INSERT INTO Evidence (evaluation_id, evidence_url, evidence_title, evidence_snippet,
                                   retrieved_timestamp, language, relevance_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        evidence_timestamp = datetime.now(timezone.utc)
        for evidence in evidence_list:
            cursor.execute(sql_evidence, (
                evaluation_id, evidence.get('url'), evidence.get('title'), evidence.get('snippet'),
                evidence_timestamp, 'sv', evidence.get('relevance_score')
            ))
        print("Evidence inserted.")
        # 5. Commit Transaction
        conn.commit()
        print("Transaction committed successfully.")
        return True
    except psycopg2.Error as e:
        print(f"ERROR: Database error during storage: {e}")
        if conn: conn.rollback(); print("Transaction rolled back.")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error during storage: {e}")
        if conn: conn.rollback(); print("Transaction rolled back.")
        return False
    finally:
        if cursor: cursor.close()


# --- Main Execution Logic ---
if __name__ == "__main__":
    print("Starting Claim Verification Process...")
    db_conn = get_db_connection() # Get DB connection here

    twitter_search_query = '#svpol'
    max_tweets_to_fetch = 1 # Still fetching only one

    # --- Fetch Tweets using Requests function ---
    tweets = fetch_tweets_requests(twitter_search_query, max_tweets_to_fetch) # <--- Call the new function

    # --- Process the single fetched tweet ---
    if not tweets:
        print("No tweet fetched matching the criteria. Exiting.")
        if db_conn:
            db_conn.close()
        sys.exit(0)

    # The rest of the loop and processing logic remains the same
    for tweet in tweets:
        # Process tweet
        print(f"Processing tweet: {tweet['id']}")
        claim_text = tweet['text']
        
        # Search for evidence
        search_query = claim_text.split('#', 1)[0].strip()
        search_results = search_web_tavily(search_query, max_results=5)
        
        # Evaluate claim
        evaluation = evaluate_claim_with_llm(claim_text, search_results)
        
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
        store_verification_data(db_conn, source_data, claim_data, evaluation_data, search_results)

    # --- Cleanup ---
    if db_conn:
        db_conn.close()
        print("Database connection closed.")

    print("Claim Verification Process Finished.")