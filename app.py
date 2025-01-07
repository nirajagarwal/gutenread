from quart import Quart, render_template, jsonify, request
import aiohttp
import urllib.parse
import logging
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import asyncio

# Add logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Quart(__name__)

load_dotenv()  # Load environment variables from .env file
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Cache storage
trending_cache = {
    'openlibrary': {'data': None, 'timestamp': None},
    'gutenberg': {'data': None, 'timestamp': None}
}

# Cache duration
CACHE_DURATION = timedelta(hours=24)

# Add at the top of your file, with other constants
RESULTS_LIMIT = 8

async def is_cache_valid(cache_type):
    """Check if cache is valid"""
    cache = trending_cache[cache_type]
    if not cache['timestamp']:
        return False
    return datetime.now() - cache['timestamp'] < CACHE_DURATION

@app.route("/")
async def index():
    logger.debug("Index route accessed")
    return await render_template("index.html")

@app.route("/search/gutenberg/<query>")
async def search_gutenberg(query):
    """Search books using Gutenberg API"""
    base_url = "https://gutendex.com/books"
    params = {
        "search": query,
        "page": 1,
        "per_page": RESULTS_LIMIT
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                # Ensure we only return RESULTS_LIMIT books
                if 'results' in data:
                    data['results'] = data['results'][:RESULTS_LIMIT]
                return data
            return {"error": "Failed to fetch results", "status": response.status}

@app.route("/search/google/<query>")
async def search_google_books(query):
    """Search books using Google Books API"""
    base_url = "https://www.googleapis.com/books/v1/volumes"
    
    params = {
        "q": query,
        "filter": "free-ebooks",
        "printType": "books",
        "maxResults": 8,  # Changed from 40 to 8
        "key": GOOGLE_API_KEY
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(base_url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                # Filter to only include books with full text available
                available_books = [
                    book for book in data.get("items", [])
                    if book.get("accessInfo", {}).get("viewability", "") == "ALL_PAGES"
                ]
                
                return {
                    "total": len(available_books),
                    "books": [
                        {
                            "title": book["volumeInfo"].get("title", ""),
                            "authors": book["volumeInfo"].get("authors", []),
                            "cover_url": book["volumeInfo"].get("imageLinks", {}).get("thumbnail", None),
                            "formats": {
                                "application/epub+zip": book["accessInfo"].get("epub", {}).get("downloadLink"),
                                "text/html": book["volumeInfo"].get("previewLink")
                            }
                        }
                        for book in available_books
                    ]
                }
            return {"error": "Failed to fetch results", "status": response.status}

@app.route("/search/doab/<query>")
async def search_doab(query):
    """Search books using DOAB API"""
    base_url = "https://directory.doabooks.org/rest/search"
    params = {
        "query": f"title:{query}",
        "filter": "type:monograph",
        "expand": "metadata",
        "limit": RESULTS_LIMIT,
        "format": "json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Accept": "application/json"
            }
            
            async with session.get(base_url, params=params, headers=headers) as response:
                if response.status == 200:
                    items = await response.json()
                    books = []
                    
                    for item in items[:RESULTS_LIMIT]:
                        try:
                            metadata_list = item.get('metadata', [])
                            book_data = {}
                            
                            # Process each metadata entry
                            for meta in metadata_list:
                                key = meta.get('key', '')
                                value = meta.get('value', '')
                                
                                if key == 'dc.title':
                                    book_data['title'] = value
                                elif key == 'dc.contributor.editor':
                                    if 'authors' not in book_data:
                                        book_data['authors'] = []
                                    book_data['authors'].append(value)
                                elif key == 'dc.description.abstract':
                                    book_data['abstract'] = value
                                elif key == 'dc.identifier.uri':
                                    book_data['url'] = value
                                elif key == 'oapen.identifier.doi':
                                    book_data['doi'] = value
                            
                            # Get handle for cover image
                            handle = item.get('handle', '')
                            if handle:
                                # Construct cover URL using handle
                                book_data['cover_url'] = f"https://directory.doabooks.org/bitstream/handle/{handle}/external_content.pdf.jpg?sequence=1&isAllowed=y"
                            
                            # Only add books that have at least a title
                            if book_data.get('title'):
                                books.append({
                                    'title': book_data.get('title', 'Unknown Title'),
                                    'authors': book_data.get('authors', []),
                                    'abstract': book_data.get('abstract', ''),
                                    'url': book_data.get('url', ''),
                                    'doi': book_data.get('doi'),
                                    'cover_url': book_data.get('cover_url')
                                })
                                
                        except Exception as e:
                            logger.error(f"Error processing DOAB item: {str(e)}")
                            continue
                    
                    return {"books": books}
                return {"error": "Failed to fetch results", "status": response.status}
    except Exception as e:
        logger.error(f"Error fetching DOAB results: {str(e)}")
        return {"error": str(e)}

@app.route("/test/doab")
async def test_doab():
    """Test DOAB API with a simple query"""
    query = "science"  # A term likely to return results
    base_url = "https://directory.doabooks.org/rest/search"
    
    params = {
        "query": query,
        "expand": "metadata",
        "limit": 1
    }
    
    headers = {
        "Accept": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, headers=headers) as response:
                status = response.status
                try:
                    data = await response.json()
                    return {
                        "status": status,
                        "data": data,
                        "items_found": len(data.get("items", [])),
                        "raw_response": str(data)[:500]  # First 500 chars of response
                    }
                except Exception as e:
                    return {
                        "status": status,
                        "error": str(e),
                        "raw_response": await response.text()
                    }
    except Exception as e:
        return {"error": str(e)}

# Add new routes for trending/featured books
@app.route("/trending/openlibrary")
async def trending_openlibrary():
    """Get trending books from OpenLibrary with caching"""
    # Add debug logging
    logger.debug(f"OpenLibrary cache status: {trending_cache['openlibrary']}")
    
    if await is_cache_valid('openlibrary'):
        logger.debug("Returning cached OpenLibrary trending data")
        return trending_cache['openlibrary']['data']

    logger.debug("Fetching fresh trending OpenLibrary books")
    base_url = "https://openlibrary.org/search.json"
    
    params = {
        "q": "public domain",
        "sort": "rating",
        "limit": RESULTS_LIMIT
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {
                        "books": [{
                            "title": book.get("title", ""),
                            "authors": book.get("author_name", []),
                            "cover_id": book.get("cover_i"),
                            "key": book.get("key", ""),
                            "availability": book.get("availability", {})
                        } for book in data.get("docs", [])[:RESULTS_LIMIT]]
                    }
                    
                    # Update cache with timestamp
                    trending_cache['openlibrary'] = {
                        'data': result,
                        'timestamp': datetime.now()
                    }
                    logger.debug("Updated OpenLibrary cache")
                    return result
                return {"error": "Failed to fetch results", "status": response.status}
    except Exception as e:
        logger.error(f"Error fetching OpenLibrary trending: {str(e)}")
        return {"error": str(e), "status": 500}

@app.route("/trending/gutenberg")
async def trending_gutenberg():
    """Get popular books from Project Gutenberg with caching"""
    # Add debug logging
    logger.debug(f"Gutenberg cache status: {trending_cache['gutenberg']}")
    
    if await is_cache_valid('gutenberg'):
        logger.debug("Returning cached Gutenberg trending data")
        return trending_cache['gutenberg']['data']

    logger.debug("Fetching fresh trending Gutenberg books")
    base_url = "https://gutendex.com/books"
    params = {
        "sort": "popular"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    result = {
                        "results": data.get("results", [])[:RESULTS_LIMIT]
                    }
                    
                    # Update cache with timestamp
                    trending_cache['gutenberg'] = {
                        'data': result,
                        'timestamp': datetime.now()
                    }
                    logger.debug("Updated Gutenberg cache")
                    return result
                return {"error": "Failed to fetch results", "status": response.status}
    except Exception as e:
        logger.error(f"Error fetching Gutenberg trending: {str(e)}")
        return {"error": str(e), "status": 500}

@app.route("/search/openlibrary/<query>")
async def search_openlibrary(query):
    """Search books using Open Library API"""
    base_url = "https://openlibrary.org/search.json"
    
    # Fields we want to retrieve
    fields = [
        "key", "title", "author_name", "first_publish_year",
        "cover_i", "edition_count", "availability",
        "isbn", "language", "publisher", "ia"
    ]
    
    params = {
        "q": query,
        "fields": ",".join(fields),
        "limit": 8
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    logger.debug(f"Searching OpenLibrary with URL: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                
                # Filter results to include books with Internet Archive IDs
                available_books = [
                    book for book in data.get("docs", [])
                    if book.get("ia")
                ]
                
                return {
                    "total": len(available_books),
                    "books": [
                        {
                            "title": book.get("title", ""),
                            "authors": book.get("author_name", []),
                            "first_publish_year": book.get("first_publish_year"),
                            "cover_id": book.get("cover_i"),
                            "edition_count": book.get("edition_count", 0),
                            "languages": book.get("language", []),
                            "publishers": book.get("publisher", []),
                            "isbn": book.get("isbn", []),
                            "key": book.get("key", ""),
                            "ia": book.get("ia", []),
                            "availability": book.get("availability", {})
                        }
                        for book in available_books
                    ]
                }
            return {"error": "Failed to fetch results", "status": response.status}

# Optional: Add a background task to refresh cache periodically
async def refresh_cache():
    """Background task to refresh cache before it expires"""
    while True:
        try:
            logger.debug("Cache refresh cycle starting")
            # Wait until cache is close to expiring (90% of cache duration)
            await asyncio.sleep(CACHE_DURATION.total_seconds() * 0.9)
            
            # Refresh both caches
            await trending_openlibrary()
            await trending_gutenberg()
            
            logger.info("Cache refreshed successfully")
        except Exception as e:
            logger.error(f"Error refreshing cache: {str(e)}")

# Start the background task when the app starts
@app.before_serving
async def startup():
    """Start background tasks when app starts"""
    logger.info("Starting cache refresh background task")
    app.background_tasks.add(asyncio.create_task(refresh_cache()))

if __name__ == "__main__":
    app.run(deug=False)