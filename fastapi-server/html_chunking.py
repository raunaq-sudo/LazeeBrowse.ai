from bs4 import BeautifulSoup, NavigableString, Tag
import re
from typing import List, Dict

# -------------------------------
# Config
# -------------------------------
MAX_WORDS = 700
MIN_WORDS = 50


# -------------------------------
# Helper: Clean Text
# -------------------------------
def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# -------------------------------
# Rule: Ignore noisy divs
# -------------------------------
def is_valid_div(tag: Tag) -> bool:
    """
    Ignore divs that ONLY have class attribute
    """
    if tag.name != "div":
        return True

    attrs = tag.attrs.keys()

    # Only 'class' exists → ignore
    if len(attrs) == 1 and "class" in attrs:
        return False

    return True


# -------------------------------
# Extract meaningful blocks
# -------------------------------
def extract_blocks(soup: BeautifulSoup) -> List[Dict]:
    blocks = []
    current_section = {"header": None, "content": []}

    for tag in soup.find_all(True):

        # Skip invalid divs
        if tag.name == "div" and not is_valid_div(tag):
            continue

        # Headers define new sections
        if tag.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            if current_section["content"]:
                blocks.append(current_section)

            current_section = {
                "header": clean_text(tag.get_text()),
                "content": []
            }

        # Content tags
        elif tag.name in ["p", "li", "span", "a"]:
            text = clean_text(tag.get_text())
            if text:
                current_section["content"].append(text)

    # Append last section
    if current_section["content"]:
        blocks.append(current_section)

    return blocks


# -------------------------------
# Chunk section into RAG chunks
# -------------------------------
def chunk_section(header: str, content: List[str]) -> List[Dict]:
    chunks = []
    buffer = []

    for sentence in content:
        buffer.append(sentence)

        word_count = len(" ".join(buffer).split())

        if word_count >= MAX_WORDS:
            chunks.append({
                "header": header,
                "text": " ".join(buffer)
            })
            buffer = []

    # leftover
    if buffer:
        chunks.append({
            "header": header,
            "text": " ".join(buffer)
        })

    return chunks


# -------------------------------
# Main Chunking Function
# -------------------------------
def chunk_html(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "lxml")

    # Remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    blocks = extract_blocks(soup)

    final_chunks = []

    for block in blocks:
        header = block["header"]
        content = block["content"]

        chunks = chunk_section(header, content)

        for c in chunks:
            if len(c["text"].split()) >= MIN_WORDS:
                final_chunks.append(c)

    return final_chunks


# -------------------------------
# Example Usage
# -------------------------------
if __name__ == "__main__":
    with open("page.html", "r", encoding="utf-8") as f:
        html = f.read()

    chunks = chunk_html(html)

    for i, chunk in enumerate(chunks[:5]):
        print(f"\n--- Chunk {i+1} ---")
        print("Header:", chunk["header"])
        print("Text:", chunk["text"][:300])