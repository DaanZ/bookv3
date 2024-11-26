from bs4 import BeautifulSoup

from util.files import json_write_file

# Load the HTML file
with open("data/books.html", "r", encoding="utf-8") as file:
    soup = BeautifulSoup(file, "html.parser")

# Find the tbody with the id 'booksBody'
books_body = soup.find("tbody", id="booksBody")

# Initialize a list to store parsed data
books_data = []


# Iterate through all the rows (tr)
def extract_name(row, class_name):
    value = row.find("td", class_=class_name)
    if value is not None:
        return value.text.replace(class_name.replace("_", " "), "").strip()
    else:
        return ""


if books_body:
    rows = books_body.find_all("tr")
    for row in rows:
        # Extract all the required information from td elements
        classes = ["title", "author", "isbn", "isbn13", "asin", "num_pages", "avg_rating", "num_ratings", "date_pub",
                   "date_pub_edition", "shelves", "review", "notes", "comments", "votes", "read_count", "date_started",
                   "date_read", "date_added", "owned"]
        book = {class_name: extract_name(row, class_name) for class_name in classes}
        books_data.append(book)

# Print the parsed data
for book in books_data:
    print(book)

json_write_file("data/books.json", books_data)
