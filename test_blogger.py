import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# This scope gives the script permission to manage your Blogger account
SCOPES = ['https://www.googleapis.com/auth/blogger']
BLOG_ID = '6489684370414144848' # Paste your Blog ID numbers here

def authenticate_blogger():
    print("Authenticating with Google...")
    creds = None
    
    # Check if we already logged in previously (saved in token.json)
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # If not logged in, open the browser to authenticate
    if not creds or not creds.valid:
        # Note: Make sure your JSON file is named exactly client_secrets.json
        flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Save the credentials so we don't have to log in every single time
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('blogger', 'v3', credentials=creds)

def create_test_post(service):
    print("Creating a test post...")
    
    # The payload we are sending to Blogger
    post_body = {
        "title": "Automated Python Test",
        "content": "<h2>Success!</h2><p>My Python script is officially talking to Blogger.</p>"
    }
    
    # Push the post to the blog
    posts = service.posts()
    request = posts.insert(blogId=BLOG_ID, body=post_body, isDraft=False)
    response = request.execute()
    
    print(f"\nPost published successfully!")
    print(f"Check it out here: {response.get('url')}")

if __name__ == '__main__':
    # Run the process
    blogger_service = authenticate_blogger()
    create_test_post(blogger_service)