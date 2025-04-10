# test_tweepy.py
import tweepy
import sys
import traceback # Import traceback for detailed error printing

# --- IMPORTANT ---
# 1. Replace the placeholder below with your ACTUAL Bearer Token string.
# 2. Paste it directly between the quotes "".
# 3. REMEMBER TO DELETE THIS FILE OR REMOVE YOUR TOKEN AFTER TESTING.
TEST_BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAB0U0gEAAAAAEMHgLSVLqjSNu%2FZCmoPMTuaeyGI%3DGjt2t1bgau4Ps8KKALvwh7avOcYBYfDI1xcGeL32A9BO6hsFjc"
# --- IMPORTANT ---


print(f"--- Minimal Tweepy Initialization Test ---")
print(f"Tweepy version: {tweepy.__version__}") # Print version being tested
print(f"Using hardcoded Bearer Token.")

# Basic check on the hardcoded token to ensure it was replaced
if not isinstance(TEST_BEARER_TOKEN, str) or not TEST_BEARER_TOKEN or TEST_BEARER_TOKEN == "PASTE_YOUR_ACTUAL_BEARER_TOKEN_HERE":
    print("\nERROR: Please replace 'PASTE_YOUR_ACTUAL_BEARER_TOKEN_HERE' with your real Bearer Token string in the script.")
    sys.exit(1)

# Optional: Print type and first few chars for confirmation
# print(f"Token Type: {type(TEST_BEARER_TOKEN)}")
# print(f"Token Starts With: {TEST_BEARER_TOKEN[:5]}...")

try:
    print("\nAttempting to initialize tweepy.Client(bearer_token=...).")
    # Initialize the client using only the hardcoded bearer token
    client = tweepy.Client(bearer_token=TEST_BEARER_TOKEN)

    # If the above line succeeds without error, initialization worked.
    print("\nSUCCESS: tweepy.Client() initialization call completed without error.")

    # OPTIONAL TEST: Try a simple read-only API call that works with Bearer Token.
    # Replace 'elonmusk' with any public account username.
    # This helps confirm the token is valid for API calls, not just initialization.
    try:
        print("\nAttempting client.get_user(username='elonmusk')...")
        response = client.get_user(username='elonmusk')
        print(f"SUCCESS: client.get_user() call succeeded.")
        # print(f"Response data (first 100 chars): {str(response)[:100]}...") # Uncomment to see response
    except Exception as api_call_e:
        print(f"\nWARNING: API call failed after successful initialization.")
        print(f"API Call Error: {api_call_e}")
        print("(This might be expected depending on API permissions or token validity,")
        print(" but initialization itself succeeded.)")


except Exception as e:
    # This block catches errors during the tweepy.Client() initialization itself
    print(f"\nERROR: Failed during tweepy.Client initialization.")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Message: {e}")
    print("\n--- Full Traceback ---")
    traceback.print_exc() # Print the detailed traceback to see where the error occurs
    print("----------------------")
    sys.exit(1) # Exit with error status

print("\n--- Minimal Test Script Finished ---")