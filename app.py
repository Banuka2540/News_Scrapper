import os
import requests
import time
import re
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- CONFIGURATION ---
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
BLOG_ID = os.environ.get("BLOG_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([RAPIDAPI_KEY, BLOG_ID, GEMINI_API_KEY]):
    raise ValueError("Missing one or more API keys in environment variables!")

SCOPES = ['https://www.googleapis.com/auth/blogger']

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

def fetch_sri_lankan_news():
    """Fetches the top news links from RapidAPI."""
    print("1. Fetching news list from RapidAPI...")
    url = "https://latest-sri-lankan-news.p.rapidapi.com/latest-news/adaderana/v1"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "latest-sri-lankan-news.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def get_already_published_urls(service):
    """Fetches recent posts from Blogger and finds the hidden source URLs."""
    print("2. Checking your blog for previously published articles...")
    published_urls = set()
    try:
        request = service.posts().list(blogId=BLOG_ID, maxResults=20).execute()
        posts = request.get('items', [])
        
        for post in posts:
            content = post.get('content', '')
            match = re.search(r'<span style="display:none;" data-source="(.*?)"></span>', content)
            if match:
                published_urls.add(match.group(1))
        
        print(f"   -> Found {len(published_urls)} articles we already published.")
        return published_urls
    except Exception as e:
        print(f"   -> Error reading past posts: {e}")
        return published_urls

def scrape_full_article(url):
    """Visits the news URL and scrapes the text."""
    try:
        if not url.startswith("http"):
            url = "https://www.adaderana.lk/" + url.lstrip("/")
        page = requests.get(url)
        soup = BeautifulSoup(page.content, 'html.parser')
        paragraphs = soup.find_all('p')
        full_text = " ".join([p.get_text() for p in paragraphs])
        if len(full_text) < 100: return None
        return full_text
    except Exception as e:
        return None

def rewrite_with_gemini_in_sinhala(original_text):
    """Asks Gemini to rewrite the text into a fresh HTML blog post in Sinhala."""
    print("   -> Translating and rewriting article into Sinhala...")
    
    # We explicitly tell Gemini to output the headline and body in Sinhala
    prompt = f"""
    You are an expert Sri Lankan news blogger. Read the following English news article and rewrite it completely in fluent, professional Sinhala. 
    1. Create a brand new, catchy headline in Sinhala, wrapped in <h1> tags.
    2. Write the body of the article in proper HTML using <p> tags, entirely in Sinhala.
    3. Do NOT include any markdown formatting (like ```html). Output pure HTML only.
    Text to translate and rewrite: {original_text}
    """
    try:
        response = model.generate_content(prompt)
        html_output = response.text.strip()
        if html_output.startswith("```html"):
            html_output = html_output[7:-3]
        return html_output
    except Exception as e:
        print(f"   -> Gemini Error: {e}")
        return None

if __name__ == "__main__":
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        blogger_service = build('blogger', 'v3', credentials=creds)
    else:
        print("Error: token.json not found. Run your test script first.")
        exit()

    news_data = fetch_sri_lankan_news()
    published_urls = get_already_published_urls(blogger_service)
    
    if news_data:
        try:
            articles = news_data["latestContent"]["hot_news"]
        except KeyError:
            print("Could not parse news data.")
            exit()
            
        print(f"\nProcessing articles...")
        
        for index, article in enumerate(articles[:5]):
            original_url = article.get('source')
            
            if original_url in published_urls:
                print(f"\n--- Skipping: We already published this news! ---")
                continue
                
            print(f"\n--- Processing New Article ---")
            
            full_text = scrape_full_article(original_url)
            if not full_text:
                continue
            
            # Rewrite and translate
            rewritten_html = rewrite_with_gemini_in_sinhala(full_text)
            if not rewritten_html:
                continue
                
            # Add our invisible tracking tag to the bottom
            tracking_tag = f'\n<span style="display:none;" data-source="{original_url}"></span>'
            final_content = rewritten_html + tracking_tag
            
            # Extract Title (which will now be in Sinhala)
            post_title = "Latest News Update"
            if "<h1>" in final_content and "</h1>" in final_content:
                start = final_content.find("<h1>") + 4
                end = final_content.find("</h1>")
                post_title = final_content[start:end]
                final_content = final_content.replace(f"<h1>{post_title}</h1>", "")

            # Publish
            print(f"   -> Publishing: {post_title}")
            try:
                post_body = {"title": post_title, "content": final_content}
                request = blogger_service.posts().insert(blogId=BLOG_ID, body=post_body, isDraft=False)
                response = request.execute()
                print(f"   -> SUCCESS! View post: {response.get('url')}")
            except Exception as e:
                print(f"   -> Publishing Error: {e}")
            
            time.sleep(5)
            
        print("\nPipeline finished successfully!")