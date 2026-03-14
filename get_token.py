from google_auth_oauthlib.flow import InstalledAppFlow

# The permission we need (Blogger access)
SCOPES = ['https://www.googleapis.com/auth/blogger']

def generate_new_token():
    print("Opening your web browser to authenticate...")
    
    # This reads your client_secrets.json and asks Google for a login screen
    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    # This saves your successful login as the token.json VIP pass!
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        
    print("\nSUCCESS! Look in your folder. Your token.json file has been created!")

if __name__ == '__main__':
    generate_new_token()