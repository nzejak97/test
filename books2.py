import json
from functools import wraps
from typing import Optional

import redis
from fastapi import FastAPI, Path, Query, HTTPException, Body
from pydantic import BaseModel, Field
from starlette import status

app = FastAPI()
redis_client = redis.Redis(host='localhost', port=6379, db=0)


def cache_response(ttl_seconds: int):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Construct a unique key based on the function name and its arguments
            key = f"{func.__name__}:{args}:{kwargs}"

            # Check if the result is already cached
            cached_result = redis_client.get(key)
            if cached_result:
                return json.loads(cached_result)

            # If not cached, execute the function and cache the result
            result = await func(*args, **kwargs)
            if isinstance(result, list):
                result_list = []
                for i in range(len(result)):
                    result_list.append(json.dumps(result[i].__dict__))
                    redis_client.set(key, json.dumps(result_list))
                    redis_client.expire(key, ttl_seconds)
                return result_list
            else:
                redis_client.set(key, json.dumps(result.__dict__))
                redis_client.expire(key, ttl_seconds)
                return result

        return wrapper

    return decorator


class Book:
    id: int
    title: str
    author: str
    description: str
    rating: int
    published_date: int

    def __init__(self, id, title, author, description, rating, published_date):
        self.id = id
        self.title = title
        self.author = author
        self.description = description
        self.rating = rating
        self.published_date = published_date


class BookRequest(BaseModel):
    id: Optional[int] = None
    title: str = Field(min_length=3)
    author: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=100)
    rating: int = Field(gt=0, lt=6)
    published_date: int = Field(gt=1999, lt=2031)

    class Config:
        json_schema_extra = {
            'example': {
                'title': 'A new book',
                'author': 'codingwithroby',
                'description': 'A new description of a book',
                'rating': 5,
                'published_date': 2029
            }
        }


# BOOKS = [
#     Book(1, 'Computer Science Pro', 'codingwithroby', 'A very nice book!', 5, 2030),
#     Book(2, 'Be Fast with FastAPI', 'codingwithroby', 'A great book!', 5, 2030),
#     Book(3, 'Master Endpoints', 'codingwithroby', 'A awesome book!', 5, 2029),
#     Book(4, 'HP1', 'Author 1', 'Book Description', 2, 2028),
#     Book(5, 'HP2', 'Author 2', 'Book Description', 3, 2027),
#     Book(6, 'HP3', 'Author 3', 'Book Description', 1, 2026)
# ]
BOOKS = []


@app.get("/books", status_code=status.HTTP_200_OK)
@cache_response(ttl_seconds=600)
async def read_all_books():
    return BOOKS


@app.get("/books/{book_id}", status_code=status.HTTP_200_OK)
async def read_book(book_id: int = Path(gt=0)):
    for book in BOOKS:
        if book.id == book_id:
            return book
    raise HTTPException(status_code=404, detail='Item not found')


@app.get("/books/", status_code=status.HTTP_200_OK)
@cache_response(ttl_seconds=600)
async def read_book_by_rating(book_rating: int = Query(gt=0, lt=6)):
    books_to_return = []
    for book in BOOKS:
        if book.rating <= book_rating:
            books_to_return.append(book)
    return books_to_return


@app.get("/books/publish/", status_code=status.HTTP_200_OK)
async def read_books_by_publish_date(published_date: int = Query(gt=1999, lt=2031)):
    books_to_return = []
    for book in BOOKS:
        if book.published_date == published_date:
            books_to_return.append(book)
    return books_to_return


@app.post("/create-book", status_code=status.HTTP_201_CREATED)
@cache_response(ttl_seconds=600)
async def create_book(book_request: BookRequest):
    new_book = Book(**book_request.model_dump())
    BOOKS.append(find_book_id(new_book))
    return new_book


def find_book_id(book: Book):
    book.id = 1 if len(BOOKS) == 0 else BOOKS[-1].id + 1
    return book


@app.put("/books/update_book", status_code=status.HTTP_204_NO_CONTENT)
async def update_book(book: BookRequest):
    book_changed = False
    for i in range(len(BOOKS)):
        if BOOKS[i].id == book.id:
            BOOKS[i] = book
            book_changed = True
    if not book_changed:
        raise HTTPException(status_code=404, detail='Item not found')


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(book_id: int = Path(gt=0)):
    book_changed = False
    for i in range(len(BOOKS)):
        if BOOKS[i].id == book_id:
            BOOKS.pop(i)
            book_changed = True
            break
    if not book_changed:
        raise HTTPException(status_code=404, detail='Item not found')


# Endpoint to list all keys in Redis cache
@app.get("/redis/keys")
async def list_redis_keys():
    try:
        keys = redis_client.keys("*")
        return {"keys": keys}
    except Exception as e:
        return {"error": str(e)}


# Endpoint to get the value of a specific key from Redis cache
@app.get("/redis/get/{key}")
async def get_redis_value(key: str):
    value = redis_client.get(key)
    return value
