import json
import os
import re

# Windows refuses a path over 260 characters, and a book title is long enough to reach it
# on its own: "The Gardener and the Carpenter: What the New Science of Child Development
# Tells Us…" landed at exactly 260 and the upload failed with FileNotFoundError, which
# reads as a missing directory rather than a name that will not fit.
#
# 120 leaves room for the repo path, the books/available prefix and the "-2" a duplicate
# gets. The name is a label — the book's identity lives in its meta — so cutting it costs
# nothing.
MAX_FILENAME = 120


def write_to_file(path, data):
    # Open a file in write mode
    with open(path, "w", encoding="utf-8") as file:
        # Write each item in the list to the file
        file.write(data)


def json_write_file(path, data):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4)


def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        return None
    except Exception as e:
        return None


def json_read_file(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None


def sanitize_filename(filename):
    # Define a regex pattern to match invalid characters
    filename = filename.replace("https://", "").replace("www.", "").replace("http://", "").replace(" ", "_")
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
    # Replace invalid characters with an underscore
    sanitized = re.sub(invalid_chars, '', filename)
    # Remove leading or trailing spaces and periods
    sanitized = sanitized.strip(' .')

    # Bound the length, keeping the extension: a name that will not fit fails at open()
    # with an error about the directory, which sends you looking in the wrong place.
    if len(sanitized) > MAX_FILENAME:
        stem, extension = os.path.splitext(sanitized)
        stem = stem[: max(1, MAX_FILENAME - len(extension))].rstrip(' ._-')
        sanitized = stem + extension
    return sanitized


def is_valid_url(url, base_url):
    # This regular expression matches URLs ending with .html or URLs without any extension
    text = url[len(base_url):]
    if "." in text:
        return text.endswith(".html")
    elif "#" in text:
        return False
    else:
        return True


def process_double_newlines(content):
    while '\n\n' in content:
        content = content.replace('\n\n', '\n')
    return content
