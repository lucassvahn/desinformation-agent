import os
import requests
import json
import praw
from urllib.parse import urlparse

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
    """Extract article content with newspaper3k which respects robot rules"""
    try:
        from newspaper import Article
        
        article = Article(url)
        article.download()
        article.parse()
        
        # Return a structured result with article info
        return {
            "success": True,
            "title": article.title,
            "text": article.text[:2000] + "..." if len(article.text) > 2000 else article.text,
            "authors": article.authors
        }
    except Exception as e:
        print(f"Failed to extract content from {url}: {e}")
        return {"success": False, "error": str(e)}


def fetch_reddit_claims_for_llm(max_results=10, client_id=None, client_secret=None, user_agent="python:desinformation-agent:v0.0.1 (by u/laughingmaymays)", subreddit="svenskpolitik", extract_links=True):
    """Fetches Reddit posts and formats them for LLM evaluation as search result snippets."""
    import praw
    from urllib.parse import urlparse
    print(f"Fetching up to {max_results} Reddit posts in r/{subreddit}")

    # Load credentials from env if not passed
    client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
    client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "python:desinformation-agent:v0.0.1 (by u/laughingmaymays)")

    if not all([client_id, client_secret, user_agent]):
        print("ERROR: Missing Reddit API credentials.")
        return []

    reddit_results = []

    try:
        reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
        search_results = reddit.subreddit(subreddit).new(limit=max_results)

        for submission in search_results:
            result = {
                "url": f"https://www.reddit.com{submission.permalink}",
                "title": submission.title,
                "snippet": submission.selftext[:300] + "..." if submission.selftext else "(No content)"
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
                    if article_data["authors"]:
                        result["link_authors"] = article_data["authors"]
                else:
                    result["link_error"] = article_data["error"]
                
            reddit_results.append(result)

        print(f"Found {len(reddit_results)} Reddit posts.")

    except Exception as e:
        print(f"ERROR: Failed to fetch Reddit posts: {e}")
        import traceback
        traceback.print_exc()
        return []

    return reddit_results