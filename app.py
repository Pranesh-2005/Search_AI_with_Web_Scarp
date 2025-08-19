import os
import asyncio
import requests
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

def search_serper(query):
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query}
    response = requests.post("https://google.serper.dev/search", headers=headers, json=payload)
    results = response.json()

    # Return both snippets and URLs for crawling
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

    return search_results

async def crawl_to_markdown(url: str) -> str:
    """Crawl a URL and return its content as markdown."""
    try:
        browser_conf = BrowserConfig(headless=True, verbose=False)
        filter_strategy = PruningContentFilter()
        md_gen = DefaultMarkdownGenerator(content_filter=filter_strategy)
        run_conf = CrawlerRunConfig(markdown_generator=md_gen)
        
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            result = await crawler.arun(url=url, config=run_conf)
            return result.markdown.fit_markdown or result.markdown.raw_markdown or ""
    except Exception as e:
        return f"Crawl error for {url}: {str(e)}"

async def generate_answer_with_crawling(question):
    """Generate answer using search results and crawled content."""
    try:
        # 1. Get search results
        search_results = search_serper(question)
        
        # 2. Crawl each URL to get full content
        crawled_content = []
        for result in search_results:
            url = result["url"]
            title = result["title"]
            
            print(f"Crawling: {title} ({url})")
            markdown_content = await crawl_to_markdown(url)
            
            # Limit content to avoid token limits
            content_snippet = markdown_content[:2000] if markdown_content else result["snippet"]
            crawled_content.append(f"## {title}\nSource: {url}\n\n{content_snippet}\n\n")
        
        # 3. Combine all content for context
        full_context = "\n".join(crawled_content)
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant that answers questions using detailed web content. Provide citations with URLs when possible."},
            {"role": "user", "content": f"Based on the following web content, answer the question. Include relevant citations.\n\nContent:\n{full_context}\n\nQuestion: {question}"}
        ]
        
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.4,
            max_tokens=800
        )
        return response.choices[0].message.content, search_results
        
    except Exception as e:
        return f"Error: {str(e)}", []

def generate_answer(question):
    """Original function using just search snippets."""
    search_results = search_serper(question)
    
    snippets = []
    for result in search_results:
        title = result["title"]
        snippet = result["snippet"]
        url = result["url"]
        snippets.append(f"{title}: {snippet} ({url})")

    context = "\n".join(snippets)
    messages = [
        {"role": "system", "content": "You are a helpful assistant that answers using real-time search context."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
    ]
    response = client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=messages,
        temperature=0.8,
        max_tokens=800
    )
    return response.choices[0].message.content

# API Endpoints

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """Search endpoint that returns JSON response."""
    try:
        print(f"\n🔍 Search Request:")
        print(f"Question: {request.question}")
        print(f"Mode: {request.mode}")
        
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
        
        print(f"\n📋 Response Data:")
        print(json.dumps(response_data, indent=2))
        
        return response_data
        
    except Exception as e:
        error_response = {
            "answer": f"Error: {str(e)}",
            "sources": [],
            "mode": request.mode,
            "status": "error"
        }
        
        print(f"\n❌ Error Response:")
        print(json.dumps(error_response, indent=2))
        
        raise HTTPException(status_code=500, detail=error_response)

if __name__ == "__main__":
    print("🚀 Starting Search Assistant Server...")
    print("📱 Frontend: http://localhost:8000")
    print("🔧 API Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=5000)