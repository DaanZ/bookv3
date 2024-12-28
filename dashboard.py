import os
import json
import streamlit as st

# Folder containing the JSON files
BOOKS_FOLDER = "books"


# Function to get all JSON files in the folder
def get_json_files(folder):
    try:
        return [os.path.join(folder, file) for file in os.listdir(folder) if file.endswith(".json")]
    except FileNotFoundError:
        st.error(f"The folder '{folder}' does not exist.")
        return []


# Function to extract book details from a JSON file
def extract_book_details(file_path):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
        meta = data.get("meta", {})
        return {
            "Title": meta.get("title", "Unknown Title"),
            "Author": meta.get("author", "Unknown Author"),
            "Category": meta.get("category", "Unknown Author"),
            "Publisher": meta.get("publisher", "Unknown Publisher"),
            "Pages": meta.get("pages", "Unknown Pages"),
            "Image": data.get("image", None),
        }
    except (json.JSONDecodeError, FileNotFoundError):
        st.error(f"Failed to read or decode {file_path}.")
        return None


if __name__ == "__main__":
    # Streamlit app
    st.title("Available Books")
    st.write("Here are the books available in the folder:")

    # Get JSON files
    json_files = get_json_files(BOOKS_FOLDER)

    if json_files:
        # Display each book as a card
        for json_file in json_files:
            book = extract_book_details(json_file)
            if book:
                # Display a card for each book
                col1, col2 = st.columns([1, 3])
                with col1:
                    if book["Image"]:
                        st.image(book["Image"], width=100)
                    #else:
                    #st.write("No Image Available")
                with col2:
                    st.subheader(book["Title"])
                    st.write(f"**Author:** {book['Author']}")
                    st.write(f"**Publisher:** {book['Publisher']}")
                    st.write(f"**Pages:** {book['Pages']}")
    else:
        st.write("No JSON files found in the folder.")
