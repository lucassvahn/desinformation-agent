import requests
import requests.auth
import os

CLIENT = os.getenv('REDDIT_CLIENT_ID')
SECRET = os.getenv('REDDIT_CLIENT_SECRET')
USER = os.getenv('REDDIT_USERNAME')
PASSWORD = os.getenv('REDDIT_PASSWORD')

client_auth = requests.auth.HTTPBasicAuth(CLIENT, SECRET)
post_data = {"grant_type": "password", "username": USER, "password": PASSWORD}
headers = {"User-Agent": "ChangeMeClient/0.1 by YourUsername"}
response = requests.post("https://www.reddit.com/api/v1/access_token", auth=client_auth, data=post_data, headers=headers)
print(response.json())
