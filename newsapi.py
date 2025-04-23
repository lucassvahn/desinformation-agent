from datetime import datetime, timezone, timedelta
import requests
import json

def search_newsapi(query, max_results=5, language='sv', NEWSAPI_KEY=str):
    """Searches for news articles using the NewsAPI /v2/everything endpoint."""
    print(f"Searching NewsAPI for: '{query}' (Lang: {language})")
    articles_data = []
    base_url = "https://newsapi.org/v2/everything"

    if not NEWSAPI_KEY:
        print("ERROR: NEWSAPI_KEY is not configured.")
        return []

    # --- Define Parameters ---
    # Calculate 'from' date (e.g., last 7 days) to keep results recent
    # NewsAPI free tier on /everything often limited to past month anyway
    from_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')

    params = {
        'q': query,
        'apiKey': NEWSAPI_KEY,
        'language': language,
        'sortBy': 'relevancy', # Options: relevancy, popularity, publishedAt
        'pageSize': max(5, min(100, max_results)), # Ensure valid range (adjust as needed)
        'from': from_date
        # 'to': YYYY-MM-DD # Optional end date
        # 'domains': 'svt.se,dn.se' # Optional: comma-separated domains
    }

    print(f"Requesting NewsAPI URL: {base_url} with query: '{query}', from: {from_date}")

    try:
        # --- Make the GET Request ---
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Check for HTTP errors

        # --- Parse JSON Response ---
        json_response = response.json()

        # --- Check NewsAPI Status and Extract Articles ---
        if json_response.get('status') == 'ok':
            articles = json_response.get('articles', [])
            print(f"Found {len(articles)} articles via NewsAPI (Total results: {json_response.get('totalResults')}).")
            for article in articles:
                # Map to a consistent format similar to other search results
                articles_data.append({
                    'title': article.get('title'),
                    'url': article.get('url'),
                    # Use description as snippet, fallback to content if needed
                    'snippet': article.get('description') or article.get('content'),
                    'source_name': article.get('source', {}).get('name'), # Extract source name
                    'published_at': article.get('publishedAt') # Keep publication date
                })
        elif json_response.get('status') == 'error':
            print(f"ERROR: NewsAPI returned an error: {json_response.get('code')} - {json_response.get('message')}")
            return []
        else:
            print(f"WARNING: Unexpected status in NewsAPI response: {json_response.get('status')}")
            return []

    except requests.exceptions.HTTPError as http_err:
        print(f"ERROR: HTTP error occurred during NewsAPI search: {http_err}")
        print(f"Response status code: {http_err.response.status_code}")
        try:
            print(f"Response body: {http_err.response.text}")
        except Exception:
            print("Could not decode error response body.")
        return []
    except requests.exceptions.RequestException as req_err:
        print(f"ERROR: Failed NewsAPI search due to RequestException: {req_err}")
        return []
    except json.JSONDecodeError as json_err:
        print(f"ERROR: Failed to decode JSON response from NewsAPI: {json_err}")
        print(f"Response text: {response.text if 'response' in locals() else 'N/A'}")
        return []
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during NewsAPI search: {e}")
        import traceback
        traceback.print_exc()
        return []

    return articles_data
