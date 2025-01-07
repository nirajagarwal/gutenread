from quart import Quart, render_template, jsonify
import aiohttp
import urllib.parse
import logging
from dotenv import load_dotenv
import os
from hypercorn.asyncio import serve
from hypercorn.config import Config

# Add logging configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Quart(__name__)

load_dotenv()  # Load environment variables from .env file
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

async def search_books(query, page=1, limit=8):
    """
    Search books using Open Library API
    Args:
        query (str): Search query
        page (int): Page number (starts from 1)
        limit (int): Number of results per page
    Returns:
        dict: Search results containing books with metadata
    """
    base_url = "https://openlibrary.org/search.json"
    
    # Calculate offset based on page number (API uses offset)
    offset = (page - 1) * limit
    
    # Fields we want to retrieve
    fields = [
        "key", "title", "author_name", "first_publish_year",
        "cover_i", "edition_count", "availability",
        "isbn", "language", "publisher", "ia"
    ]
    
    params = {
        "q": query,
        "fields": ",".join(fields),
        "offset": offset,
        "limit": limit
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    logger.debug(f"Searching OpenLibrary with URL: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                
                # Debug: Print first result's availability data
                if data.get("docs"):
                    logger.debug(f"Sample book availability data: {data['docs'][0].get('availability', {})}")
                    logger.debug(f"Sample book IA: {data['docs'][0].get('ia', [])}")
                
                # Filter results to include books with Internet Archive IDs
                available_books = [
                    book for book in data.get("docs", [])
                    if book.get("ia")
                ]
                
                logger.debug(f"Total results: {data.get('numFound', 0)}, Available books: {len(available_books)}")
                
                return {
                    "total": len(available_books),
                    "page": page,
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

@app.route("/search/<query>")
@app.route("/search/<query>/<int:page>")
async def search(query, page=1):
    results = await search_books(query, page=page)
    return jsonify(results)

@app.route("/")
async def index():
    logger.debug("Index route accessed")
    return await render_template("index.html")

@app.route("/search/openlibrary/<query>")
@app.route("/search/openlibrary/<query>/<int:page>")
async def search_openlibrary(query, page=1):
    logger.debug(f"Searching OpenLibrary for: {query}")  # Add logging
    results = await search_books(query, page=page)
    logger.debug(f"Found {len(results.get('books', []))} results")  # Add logging
    return jsonify(results)

@app.route("/search/gutenberg/<query>")
async def search_gutenberg(query):
    """Search books using Gutenberg API"""
    base_url = "https://gutendex.com/books"
    params = {
        "search": query,
        "page": 1,
        "per_page": 8  # Limit to 8 results
    }
    
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                # Process results to include cover image URLs
                for book in data.get('results', []):
                    # Get cover image from formats if available
                    if 'image/jpeg' in book.get('formats', {}):
                        book['cover_url'] = book['formats']['image/jpeg']
                    else:
                        book['cover_url'] = None
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
    logger.debug(f"Searching DOAB for: {query}")
    
    params = {
        "query": query,
        "expand": "metadata",
        "limit": 20
    }
    
    headers = {
        "Accept": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, headers=headers) as response:
                if response.status == 200:
                    items = await response.json()
                    logger.debug(f"DOAB found {len(items)} total items")
                    
                    books = []
                    for item in items:
                        metadata = item.get("metadata", [])
                        
                        # Check if this is actually a book
                        item_type = next((meta["value"] for meta in metadata 
                                        if meta["key"] == "dc.type"), None)
                        
                        if item_type != "book":
                            continue
                            
                        # Extract required metadata
                        title = next((meta["value"] for meta in metadata 
                                    if meta["key"] == "dc.title"), None)
                        authors = [meta["value"] for meta in metadata 
                                 if meta["key"] == "dc.contributor.author"]
                        doi = next((meta["value"] for meta in metadata 
                                  if meta["key"] == "oapen.identifier.doi"), None)
                        isbn = next((meta["value"] for meta in metadata 
                                   if meta["key"] == "dc.identifier.isbn"), None)
                        abstract = next((meta["value"] for meta in metadata 
                                       if meta["key"] == "dc.description.abstract"), "")
                        publisher = next((meta["value"] for meta in metadata 
                                        if meta["key"] == "publisher.name"), "Unknown Publisher")
                        
                        if title:  # Only add if we have a title
                            books.append({
                                "title": title,
                                "authors": authors,
                                "cover_url": None,  # Will be set by frontend
                                "isbn": isbn,  # Add ISBN for cover lookup
                                "doi": doi,   # Add DOI as backup
                                "url": f"https://directory.doabooks.org/handle/{item.get('handle')}",
                                "formats": {
                                    "text/html": f"https://doi.org/{doi}" if doi else None
                                },
                                "extract": f"{abstract[:200]}... (Published by {publisher})" if abstract else f"Published by {publisher}"
                            })
                            
                            if len(books) >= 8:
                                break
                    
                    logger.debug(f"DOAB processed {len(books)} books")
                    return {
                        "total": len(books),
                        "books": books
                    }
                
                logger.error(f"DOAB API error: Status {response.status}")
                return {"error": f"Failed to fetch results: {response.status}", "status": response.status}
                
    except Exception as e:
        logger.error(f"DOAB API error: {str(e)}")
        return {"error": f"Failed to fetch results: {str(e)}", "status": 500}

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
    """Get trending books from OpenLibrary"""
    logger.debug("Fetching trending OpenLibrary books")
    base_url = "https://openlibrary.org/search.json"
    
    params = {
        "q": "public domain",
        "sort": "rating",
        "limit": 8
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                logger.debug(f"OpenLibrary trending response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"OpenLibrary trending found {len(data.get('docs', []))} books")
                    return {
                        "books": [{
                            "title": book.get("title", ""),
                            "authors": book.get("author_name", []),
                            "cover_id": book.get("cover_i"),
                            "key": book.get("key", ""),
                            "availability": book.get("availability", {})
                        } for book in data.get("docs", [])[:8]]
                    }
                return {"error": "Failed to fetch results", "status": response.status}
    except Exception as e:
        logger.error(f"Error fetching OpenLibrary trending: {str(e)}")
        return {"error": str(e), "status": 500}

@app.route("/trending/gutenberg")
async def trending_gutenberg():
    """Get popular books from Project Gutenberg"""
    logger.debug("Fetching trending Gutenberg books")
    base_url = "https://gutendex.com/books"
    params = {
        "sort": "popular"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params) as response:
                logger.debug(f"Gutenberg trending response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Gutenberg trending found {len(data.get('results', []))} books")
                    return {
                        "results": data.get("results", [])[:8]
                    }
                return {"error": "Failed to fetch results", "status": response.status}
    except Exception as e:
        logger.error(f"Error fetching Gutenberg trending: {str(e)}")
        return {"error": str(e), "status": 500}

if __name__ == "__main__":
    config = Config()
    config.bind = ["127.0.0.1:8000"]
    asyncio.run(serve(app, config)) 