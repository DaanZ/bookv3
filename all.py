import os
import json
import streamlit as st


# Folder containing the JSON files
BOOKS_FOLDER = "books/read"


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
            "path": file_path,
            ""
            "Title": meta.get("title", "Unknown Title"),
            "Author": meta.get("author", "Unknown Author"),
            "Category": meta.get("category", "Unknown Category"),
            "Publisher": meta.get("publisher", "Unknown Publisher"),
            "Pages": meta.get("pages", "Unknown Pages"),
            "Image": data.get("image", None),
            "parts": data.get("parts", [])
        }
    except (json.JSONDecodeError, FileNotFoundError):
        st.error(f"Failed to read or decode {file_path}.")
        return None


def read_books():
    json_files = get_json_files(BOOKS_FOLDER)

    if json_files:
        # Create a dropdown to select a book
        st.session_state.book_options = {}
        for json_file in json_files:
            book = extract_book_details(json_file)
            if book:
                st.session_state.book_options[book["Title"] + " - " + book["Author"]] = json_file


if __name__ == "__main__":

    if "current_book" not in st.session_state:
        st.session_state.current_book = None

    # Streamlit app
    st.title("Book Summaries")

    # Get JSON files
    if "book_options" not in st.session_state:
        read_books()

    if st.session_state.book_options:
        selected_title = st.selectbox("Select a book to read:", list(st.session_state.book_options.keys()))

        if selected_title:
            if st.session_state.current_book != selected_title:
                st.session_state.segment_index = 0
                print("reset segment index")
                st.session_state.current_book = selected_title

            selected_file = st.session_state.book_options[selected_title]
            book_details = extract_book_details(selected_file)

            if book_details:

                progress = st.empty()
                title = st.empty()
                text = st.empty()
                button = st.empty()

                def render_chunk(chunk):
                    # Define the custom CSS styles
                    if chunk["title"] not in chunk["body"]:
                        title.title(chunk["title"])
                    text.markdown(chunk["body"], unsafe_allow_html=True)

                # Display segments with navigation
                segments = book_details["parts"]

                if segments:
                    number_chunks = len(segments)
                    if st.session_state.segment_index + 1 < number_chunks:
                        if button.button("Next chunk"):
                            st.session_state.segment_index += 1
                            print("next chunk ", st.session_state.segment_index)
                        progress.progress((st.session_state.segment_index + 1) / number_chunks)
                        render_chunk(segments[st.session_state.segment_index])
                        if st.session_state.segment_index + 1 == number_chunks:
                            button.empty()
                            st.success("Finished Book: " + book_details["Title"] + " - " + book_details['Author'])

                else:
                    st.write("No segments available for this book.")
    else:
        st.write("No JSON files found in the folder.")