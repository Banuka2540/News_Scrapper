import os
import requests
import time
import re
from bs4 import BeautifulSoup
from google import genai # --- NEW GOOGLE AI LIBRARY ---
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- CONFIGURATION ---
RAPIDAPI_KEY = "95be6b90f9msh643ba3b6db91b6bp177b0djsn28f5d2180410"
BLOG_ID = "6489684370414144848"
GEMINI_API_KEY = "AIzaSyBC8BwjP33Y077TPKU5uXCCubqx-I8i4Fw"

if not all([RAPIDAPI_KEY, BLOG_ID, GEMINI_API_KEY]):
    raise ValueError("Missing one or more API keys in environment variables!")

SCOPES = ['https://www.googleapis.com/auth/blogger']

# Initialize the new Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

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
        
        return published_urls
    except Exception as e:
        print(f"   -> Error reading past posts: {e}")
        return published_urls

def scrape_full_article_and_hd_image(url):
    """Visits the news URL, scrapes the text AND the High-Def image."""
    try:
        if not url.startswith("http"):
            url = "https://www.adaderana.lk/" + url.lstrip("/")
        page = requests.get(url)
        soup = BeautifulSoup(page.content, 'html.parser')
        
        # 1. Get the full text
        paragraphs = soup.find_all('p')
        full_text = " ".join([p.get_text() for p in paragraphs])
        if len(full_text) < 100: 
            return None, None
            
        # 2. Grab the HD image from the hidden Open Graph meta tags
        hd_image_url = ""
        meta_image = soup.find("meta", property="og:image")
        if meta_image:
            hd_image_url = meta_image.get("content", "")
            
        return full_text, hd_image_url
    except Exception as e:
        return None, None

def rewrite_with_gemini_in_sinhala(original_text):
    """Asks Gemini to rewrite the text into a fresh HTML blog post in Sinhala."""
    print("   -> Translating and rewriting article into Sinhala...")
    prompt = f"""
    You are an expert Sri Lankan news blogger. Read the following English news article and rewrite it completely in fluent, professional Sinhala. 
    1. Create a brand new, catchy headline in Sinhala, wrapped in <h1> tags.
    2. Write the body of the article in proper HTML using <p> tags, entirely in Sinhala.
    3. Do NOT include any markdown formatting (like ```html). Output pure HTML only.
    Text to translate and rewrite: {original_text}
    """
    try:
        # --- NEW MODEL AND SYNTAX ---
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt
        )
        html_output = response.text.strip()
        if html_output.startswith("```html"):
            html_output = html_output[7:-3]
        elif html_output.startswith("```"):
            html_output = html_output[3:-3]
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
            api_thumbnail_url = article.get('image', '')
            
            if original_url in published_urls:
                print(f"\n--- Skipping: We already published this news! ---")
                continue
                
            print(f"\n--- Processing New Article ---")
            
            full_text, hd_image_url = scrape_full_article_and_hd_image(original_url)
            
            if not full_text:
                continue
            
            rewritten_html = rewrite_with_gemini_in_sinhala(full_text)
            if not rewritten_html:
                continue
                
            best_image_url = hd_image_url if hd_image_url else api_thumbnail_url
                
            if best_image_url:
                image_tag = f'<img src="{best_image_url}" style="width: 100%; max-width: 800px; height: auto; object-fit: cover; border-radius:8px; margin-bottom: 20px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);" alt="News image"/>\n'
                rewritten_html = rewritten_html.replace("</h1>", f"</h1>\n{image_tag}")
                
            tracking_tag = f'\n<span style="display:none;" data-source="{original_url}"></span>'
            final_content = rewritten_html + tracking_tag
            
            post_title = "Latest News Update"
            if "<h1>" in final_content and "</h1>" in final_content:
                start = final_content.find("<h1>") + 4
                end = final_content.find("</h1>")
                post_title = final_content[start:end]
                final_content = final_content.replace(f"<h1>{post_title}</h1>", "")

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