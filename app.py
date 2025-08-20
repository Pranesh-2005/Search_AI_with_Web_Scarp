import os
import ssl
import asyncio
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from openai import AzureOpenAI
from dotenv import load_dotenv
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import json

# Disable SSL warnings and configure SSL context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create permissive SSL context
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Search Assistant API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize Azure OpenAI client
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_KEY"),
    api_version="2025-01-01-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

SERPER_API_KEY = os.getenv("SERPER_API_KEY")
DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT")

class SearchRequest(BaseModel):
    question: str
    mode: str = "quick"  # "quick" or "deep"

class SearchResponse(BaseModel):
    answer: str
    sources: list
    mode: str
    status: str = "success"

def create_robust_session():
    """Create a requests session with robust retry and SSL handling."""
    session = requests.Session()
    
    # Configure retries
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        backoff_factor=1
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Disable SSL verification
    session.verify = False
    
    # Add headers to mimic a real browser
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })
    
    return session

def search_serper(query):
    """Search using Serper API with robust error handling."""
    try:
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        payload = {"q": query}
        
        # Try multiple approaches for SSL issues
        for attempt in range(3):
            try:
                print(f"🔍 Search attempt {attempt + 1} for: {query}")
                
                if attempt == 0:
                    # First try: Use robust session
                    session = create_robust_session()
                    response = session.post(
                        "https://google.serper.dev/search", 
                        headers=headers, 
                        json=payload,
                        timeout=30,
                        verify=False
                    )
                elif attempt == 1:
                    # Second try: Direct request with SSL disabled
                    response = requests.post(
                        "https://google.serper.dev/search", 
                        headers=headers, 
                        json=payload,
                        timeout=30,
                        verify=False
                    )
                else:
                    # Third try: With different SSL context
                    import ssl
                    import urllib3
                    urllib3.disable_warnings()
                    response = requests.post(
                        "https://google.serper.dev/search", 
                        headers=headers, 
                        json=payload,
                        timeout=30,
                        verify=False
                    )
                
                response.raise_for_status()
                results = response.json()
                break
                
            except (requests.exceptions.SSLError, 
                    requests.exceptions.ConnectionError,
                    ssl.SSLError) as e:
                print(f"SSL/Connection error on attempt {attempt + 1}: {e}")
                if attempt == 2:  # Last attempt
                    print("All search attempts failed, returning empty results")
                    return []
                continue
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == 2:
                    return []
                continue
        else:
            print("All search attempts failed")
            return []
        
        # Process results
        search_results = []
        for result in results.get("organic", [])[:3]:  # Limit to top 3 for crawling
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            url = result.get("link", "")
            search_results.append({
                "title": title,
                "snippet": snippet,
                "url": url
            })

        print(f"✅ Found {len(search_results)} search results")
        return search_results
        
    except Exception as e:
        print(f"❌ Critical error in search_serper: {str(e)}")
        return []

async def crawl_to_markdown(url: str) -> str:
    """Crawl a URL and return its content as markdown with enhanced error handling."""
    try:
        print(f"🕷️ Crawling: {url}")
        
        # Enhanced browser configuration for SSL issues
        browser_conf = BrowserConfig(
            headless=True, 
            verbose=False,
            browser_args=[
                "--ignore-ssl-errors=yes",
                "--ignore-certificate-errors=yes",
                "--ignore-ssl-errors-spki-list",
                "--ignore-certificate-errors-spki-list",
                "--disable-web-security",
                "--allow-running-insecure-content",
                "--disable-features=VizDisplayCompositor",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding"
            ]
        )
        
        filter_strategy = PruningContentFilter()
        md_gen = DefaultMarkdownGenerator(content_filter=filter_strategy)
        run_conf = CrawlerRunConfig(
            markdown_generator=md_gen,
            page_timeout=30000,  # 30 seconds timeout
            delay_before_return_html=2000  # 2 seconds delay
        )
        
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            result = await crawler.arun(url=url, config=run_conf)
            content = result.markdown.fit_markdown or result.markdown.raw_markdown or ""
            
            if content:
                print(f"✅ Successfully crawled {len(content)} characters from {url}")
                return content
            else:
                print(f"⚠️ No content extracted from {url}")
                return f"No content could be extracted from {url}"
                
    except asyncio.TimeoutError:
        print(f"⏱️ Timeout crawling {url}")
        return f"Timeout accessing {url}"
    except Exception as e:
        print(f"❌ Crawl error for {url}: {str(e)}")
        return f"Error accessing {url}: {str(e)}"

async def generate_answer_with_crawling(question):
    """Generate answer using search results and crawled content with enhanced error handling."""
    try:
        print(f"🔬 Starting deep search for: {question}")
        
        # 1. Get search results
        search_results = search_serper(question)
        
        if not search_results:
            return "❌ Unable to fetch search results. This might be due to network connectivity issues. Please try again later.", []
        
        # 2. Crawl each URL to get full content
        crawled_content = []
        successful_crawls = 0
        
        for i, result in enumerate(search_results):
            url = result["url"]
            title = result["title"]
            
            try:
                markdown_content = await crawl_to_markdown(url)
                
                # Limit content to avoid token limits
                if markdown_content and "error" not in markdown_content.lower():
                    content_snippet = markdown_content[:2000] if len(markdown_content) > 2000 else markdown_content
                    successful_crawls += 1
                else:
                    content_snippet = result["snippet"]  # Fallback to snippet
                
                crawled_content.append(f"## {title}\nSource: {url}\n\n{content_snippet}\n\n")
                
            except Exception as e:
                print(f"❌ Failed to crawl {url}: {e}")
                # Use snippet as fallback
                crawled_content.append(f"## {title}\nSource: {url}\n\n{result['snippet']}\n\n")
        
        print(f"📊 Successfully crawled {successful_crawls}/{len(search_results)} sources")
        
        # 3. Combine all content for context
        full_context = "\n".join(crawled_content)
        
        if not full_context.strip():
            return "❌ Unable to extract content from search results. Please try again with a different query.", search_results
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions using detailed web content. Provide citations with URLs when possible. Be comprehensive but concise."},
            {"role": "user", "content": f"Based on the following web content, answer the question thoroughly. Include relevant citations with URLs.\n\nContent:\n{full_context}\n\nQuestion: {question}"}
        ]
        
        print("🤖 Generating AI response...")
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.9,
            max_tokens=800
        )
        
        answer = response.choices[0].message.content
        print("✅ AI response generated successfully")
        
        return answer, search_results
        
    except Exception as e:
        error_msg = f"❌ Error in deep search: {str(e)}"
        print(error_msg)
        return error_msg, []

def generate_answer(question):
    """Generate answer using search snippets with enhanced error handling."""
    try:
        print(f"⚡ Starting quick search for: {question}")
        
        search_results = search_serper(question)
        
        if not search_results:
            return "❌ Unable to fetch search results. This might be due to network connectivity issues. Please try again later."
        
        snippets = []
        for result in search_results:
            title = result["title"]
            snippet = result["snippet"]
            url = result["url"]
            snippets.append(f"**{title}**: {snippet} (Source: {url})")

        context = "\n\n".join(snippets)
        
        if not context.strip():
            return "❌ No search context available. Please try again."
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions using real-time search context. Provide accurate, concise answers based on the provided information."},
            {"role": "user", "content": f"Based on the following search results, provide a comprehensive answer to the question. Include source references where relevant.\n\nSearch Results:\n{context}\n\nQuestion: {question}"}
        ]
        
        print("🤖 Generating AI response...")
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.8,
            max_tokens=800
        )
        
        answer = response.choices[0].message.content
        print("✅ AI response generated successfully")
        
        return answer
        
    except Exception as e:
        error_msg = f"❌ Error in quick search: {str(e)}"
        print(error_msg)
        return error_msg

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint for health check."""
    return {
        "message": "🔍 Search Assistant API is running!",
        "status": "healthy",
        "endpoints": {
            "search": "/search",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": json.dumps({"timestamp": "now"}),
        "version": "1.0.0"
    }

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Search endpoint that returns JSON response with enhanced error handling."""
    try:
        print(f"\n🔍 Search Request:")
        print(f"Question: {request.question}")
        print(f"Mode: {request.mode}")
        
        if not request.question or not request.question.strip():
            raise HTTPException(status_code=400, detail={
                "answer": "❌ Please provide a valid question.",
                "sources": [],
                "mode": request.mode,
                "status": "error"
            })
        
        if request.mode == "deep":
            print("🕷️ Starting deep search with web crawling...")
            answer, sources = await generate_answer_with_crawling(request.question)
        else:
            print("⚡ Starting quick search...")
            answer = generate_answer(request.question)
            sources = search_serper(request.question)
        
        response_data = {
            "answer": answer,
            "sources": sources,
            "mode": request.mode,
            "status": "success"
        }
        
        print(f"\n📋 Response Status: {response_data['status']}")
        print(f"📄 Answer Length: {len(answer)} characters")
        print(f"📚 Sources Count: {len(sources)}")
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        error_response = {
            "answer": f"❌ Unexpected error: {str(e)}",
            "sources": [],
            "mode": request.mode,
            "status": "error"
        }
        
        print(f"\n❌ Error Response:")
        print(json.dumps(error_response, indent=2))
        
        raise HTTPException(status_code=500, detail=error_response)

if __name__ == "__main__":
    print("🚀 Starting Search Assistant Server...")
    print("🌐 Server will be available at:")
    print("   • Local: http://localhost:5000")
    print("   • Health: http://localhost:5000/health")
    print("   • API Docs: http://localhost:5000/docs")
    print("=" * 50)
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=5000,
        log_level="info",
        access_log=True
    )