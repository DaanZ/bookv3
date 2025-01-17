import os

import requests
from dotenv import load_dotenv

load_dotenv()

api_url = "https://api.hardcover.app/v1/graphql"


def mark_book_as_read(title, author):
    """
    Searches for a book by title and author, then marks it as read.

    Args:
        title (str): Title of the book to search for.
        author (str): Author of the book to search for.
        api_url (str): Base URL of the GraphQL API.
        api_token (str): Bearer token for authorization.

    Returns:
        dict: API response or error message.
    """

    if ":" in title:
        title = title.split(":")[0]

    if " and " in author:
        author = author.split(" and ")[0]
    if " & " in author:
        author = author.split(" & ")[0]
    headers = {
        "Authorization": f"Bearer {os.environ['HARDCOVER_API_KEY']}"
    }

    # GraphQL query to find the book by title and author
    search_query = {
        "query": f"""
        {{
          books (
            order_by: {{users_read_count: desc}},
            where: {{
              _and: [
                {{title: {{{title}}}}},
                {{contributions: {{author: {{name: {{{author}}}}}}}}}
              ]
            }},
            limit: 5
          ) {{
            id
            title
            contributions {{
              author {{
                name
              }}
            }}
          }}
        }}
        """
    }
    print(search_query)
    response = requests.post(api_url, json=search_query, headers=headers)
    print(response.json())
    if response.status_code == 200:
        data = response.json()
        books = data.get("data", {}).get("books", [])

        if books:
            book_id = books[0].get("id")
            print("book id", book_id)

            # Mutation query to mark the book as read
            mutation_query = {
                "query": f"""
                mutation addBook {{
                  insert_user_book(object: {{book_id: {book_id}, status_id: 3}}) {{
                    id
                  }}
                }}
                """
            }

            mutation_response = requests.post(api_url, json=mutation_query, headers=headers)

            if mutation_response.status_code == 200:
                return mutation_response.json()
            else:
                return {"error": f"Failed to mark the book as read: {mutation_response.status_code} - {mutation_response.text}"}
        else:
            return {"error": "Book not found."}
    else:
        return {"error": f"Failed to search for the book: {response.status_code} - {response.text}"}


if __name__ == "__main__":
    # Example usage
    book_title = "Programming Kubernetes"
    book_author = "Michael Hausenblas"

    result = mark_book_as_read(book_title, book_author)
    print(result)
