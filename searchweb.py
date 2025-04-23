from tavily import TavilyClient # <--- Import TavilyClient
import requests
import os
import sys
# --- Updated Search Function ---
def search_web_tavily(query, max_results=5, include_domains=None, tavily_key=str):

    try:
        tavily_client = TavilyClient(api_key=tavily_key)
        print("Tavily Search Client initialized.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Tavily client: {e}")
        sys.exit(1)
    """Performs a Tavily Search for the query."""
    # Note: Tavily might not have explicit Swedish language *filtering* like Google's 'lr=lang_sv'.
    # It searches broadly. Results quality depends on the Swedish query terms and Tavily's index.
    print(f"Searching web (Tavily) for: '{query}'")
    results = []
    try:
        # Use tavily_client.search method
        # search_depth can be 'basic' or 'advanced'. 'basic' is often sufficient.
        search_params = tavily_client.search(
            query=query,
            search_depth="basic",
            max_results=max_results
            # include_domains=[], # Optional: restrict to specific domains
            # exclude_domains=[] # Optional: exclude specific domains
            )
        if include_domains:
            search_params['include_domains'] = include_domains

        response = tavily_client.search(**search_params)
        

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
