import os
import requests
import time
import re
from bs4 import BeautifulSoup
from google import genai 
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# --- CONFIGURATION (SECURED) ---
# NEVER hardcode API keys in your script. Use environment variables (e.g., in GitHub Secrets)
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
BLOG_ID = os.environ.get("BLOG_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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

def update_readme(new_posts):
    """Prepends new articles to the README.md file."""
    print(f"\n4. Updating README.md with {len(new_posts)} new articles...")
    if not os.path.exists("README.md"):
        print("   -> README.md not found. Skipping update.")
        return

    with open("README.md", "r", encoding="utf-8") as f:
        content = f.read()

    if "" not in content:
        print("   -> marker not found in README.md. Skipping.")
        return

    new_md = ""
    for post in new_posts:
        # Format the markdown to look like a blog feed
        new_md += f"### 🔴 [{post['title']}]({post['url']})\n"
        if post['image']:
            # Using HTML img tag to control the size on GitHub
            new_md += f'<a href="{post["url"]}"><img src="{post["image"]}" width="400" style="border-radius:8px;" alt="News Image"></a>\n\n'
        new_md += "---\n\n"

    # Split the file at the start marker and inject the new markdown
    parts = content.split("")
    updated_content = parts[0] + "\n" + new_md + parts[1].lstrip()

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(updated_content)
    print("   -> README.md successfully updated!")

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

def rewrite_with_gemini_in_sinhala(original_text, max_retries=3):
    """Asks Gemini to rewrite the text. Includes automatic retries for Rate Limits."""
    print("   -> Translating and rewriting article into Sinhala...")
    prompt = f"""
    You are an expert Sri Lankan news blogger. Read the following English news article and rewrite it completely in fluent, professional Sinhala. 
    1. Create a brand new, catchy headline in Sinhala, wrapped in <h1> tags.
    2. Write the body of the article in proper HTML using <p> tags, entirely in Sinhala.
    3. Do NOT include any markdown formatting (like ```html). Output pure HTML only.
    Text to translate and rewrite: {original_text}
    """
    
    # Retry Loop to handle the 429 RESOURCE_EXHAUSTED error
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt
            )
            html_output = response.text.strip()
            
            # Clean up potential markdown formatting from the response
            if html_output.startswith("```html"):
                html_output = html_output[7:-3]
            elif html_output.startswith("```"):
                html_output = html_output[3:-3]
                
            return html_output
            
        except Exception as e:
            error_msg = str(e).lower()
            if "429" in error_msg or "resource_exhausted" in error_msg or "quota" in error_msg:
                wait_time = 10 * (attempt + 1) # Wait 10s, then 20s, etc.
                print(f"   -> ⚠️ Rate limit hit. Waiting {wait_time} seconds before trying again...")
                time.sleep(wait_time)
            else:
                print(f"   -> ❌ Gemini Error: {e}")
                return None
                
    print("   -> ❌ Max retries reached. Skipping this article.")
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
            
            # Increased standard wait time to 15 seconds to safely bypass free-tier RPM limits
            time.sleep(15) 
            
        print("\nPipeline finished successfully!")