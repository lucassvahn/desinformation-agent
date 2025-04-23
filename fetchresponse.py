import os
import requests
import json
import praw
from urllib.parse import urlparse
from datetime import datetime, timedelta
import traceback

# Add LangChain imports
from langchain.document_loaders import WebBaseLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter

def fetch_tweets_requests(query, max_results=1, bearer_token=str(os.getenv("TEST_BEARER_TOKEN"))):
    """Fetches recent tweets matching the query using X API v2 and the Requests library."""
    print(f"Fetching up to {max_results} tweets via Requests for query: '{query}'")
    tweets_data = []
    search_url = "https://api.twitter.com/2/tweets/search/recent"

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

def extract_article_content(url):
    """Extract article content using LangChain's document loaders"""
    try:
        print(f"Extracting content from {url} using LangChain...")
        
        # Configure the WebBaseLoader with timeout and headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        loader = WebBaseLoader(
            web_paths=[url],
            header_template=headers,
            requests_per_second=1,
            timeout=15,
            respect_robots_txt=True
        )
        
        # Load and process the document
        docs = loader.load()
        
        if not docs:
            print(f"No content extracted from {url}")
            return {"success": False, "error": "No content extracted"}
            
        # Get the title from the metadata if available
        title = docs[0].metadata.get('title', 'Unknown Title')
        
        # Get the full text content
        full_text = docs[0].page_content
        
        # Create a text splitter for better handling of large documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=100
        )
        
        # Split the text into manageable chunks
        chunks = text_splitter.split_text(full_text)
        
        # Create summary text (use first chunk for simplicity)
        text_content = chunks[0] if chunks else "No content extracted"
        
        return {
            "success": True,
            "title": title,
            "text": text_content,
            "authors": [],
            "full_text": full_text[:10000] if len(full_text) > 10000 else full_text,  # Include full text but limit size
            "chunks": chunks[:3]  # Include up to 3 chunks for additional context
        }
    except Exception as e:
        print(f"Failed to extract content from {url} with LangChain: {e}")
        # Fall back to basic extraction if LangChain fails
        try:
            # Simple fallback using requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Try to extract title from HTML
            import re
            title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
            title = title_match.group(1) if title_match else "Unknown Title"
            
            # Get some text content (simplified)
            # Remove HTML tags and get some content
            text_content = re.sub(r'<[^>]+>', ' ', response.text)
            text_content = re.sub(r'\s+', ' ', text_content).strip()
            
            # Take a reasonable portion
            text_content = text_content[:2000] + "..." if len(text_content) > 2000 else text_content
            
            return {
                "success": True,
                "title": title,
                "text": text_content,
                "authors": []
            }
        except Exception as fallback_error:
            print(f"Fallback extraction also failed: {fallback_error}")
            return {"success": False, "error": str(e)}


def fetch_reddit_claims_for_llm(max_results=10, client_id=None, client_secret=None, user_agent="python:desinformation-agent:v0.0.1 (by u/laughingmaymays)", subreddit="svenskpolitik", extract_links=True, max_days=7):
    """Fetches recent Reddit posts from r/svenskpolitik and formats them for LLM evaluation."""
    import praw
    from urllib.parse import urlparse
    print(f"Fetching up to {max_results} Reddit posts from the last {max_days} days in r/{subreddit}")

    # Load credentials from env if not passed
    client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "python:desinformation-agent:v0.0.1 (by u/laughingmaymays)")

    if not all([client_id, client_secret, user_agent]):
        print("ERROR: Missing Reddit API credentials.")
        return []

    reddit_results = []
    # Calculate cutoff timestamp for posts
    cutoff_time = datetime.utcnow() - timedelta(days=max_days)

    try:
        reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
        
        # Fetch new posts
        search_results = reddit.subreddit(subreddit).new(limit=max_results * 2)  # Fetch more to account for filtering
        
        count = 0
        for submission in search_results:
            # Convert submission created time to datetime
            created_time = datetime.utcfromtimestamp(submission.created_utc)
            
            # Skip if older than our cutoff
            if created_time < cutoff_time:
                continue
                
            result = {
                "url": f"https://www.reddit.com{submission.permalink}",
                "title": submission.title,
                "snippet": submission.selftext[:300] + "..." if submission.selftext else "(No content)",
                "created_at": created_time.isoformat(),
                "author": str(submission.author),
                "score": submission.score
            }
            
            # Check if the submission has a link (URL posts)
            if extract_links and hasattr(submission, 'url') and submission.url and not submission.url.startswith(f"https://www.reddit.com/r/{subreddit}"):
                domain = urlparse(submission.url).netloc
                print(f"Extracting content from: {submission.url}")
                article_data = extract_article_content(submission.url)
                
                # Add article data to result
                result["link_url"] = submission.url
                result["link_domain"] = domain
                
                if article_data["success"]:
                    result["link_title"] = article_data["title"]
                    result["link_content"] = article_data["text"]
                    
                    # Add additional content from LangChain if available
                    if "chunks" in article_data and article_data["chunks"]:
                        result["link_chunks"] = article_data["chunks"]
                    if "full_text" in article_data:
                        result["link_full_text"] = article_data["full_text"]
                        
                    if article_data["authors"]:
                        result["link_authors"] = article_data["authors"]
                else:
                    result["link_error"] = article_data["error"]
                
            reddit_results.append(result)
            count += 1
            
            # Stop if we've reached our desired count
            if count >= max_results:
                break

        print(f"Found {len(reddit_results)} recent Reddit posts from the last {max_days} days.")

    except Exception as e:
        print(f"ERROR: Failed to fetch Reddit posts: {e}")
        traceback.print_exc()
        return []

    return reddit_results