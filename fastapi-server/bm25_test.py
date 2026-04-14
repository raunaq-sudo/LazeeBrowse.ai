# import json
# from langchain_community.document_loaders import RecursiveUrlLoader
# from bs4 import BeautifulSoup
# import re
# from rank_bm25 import BM25Okapi
# from rich import print

# class BM25Index:
#     def __init__(self):
#         self.docs = []
#         self.tokenized = []
#         self.bm25 = None

#     def add_documents(self, documents):
#         for doc in documents:
#             tokens = doc["text"].lower().split()
#             self.docs.append(doc)
#             self.tokenized.append(tokens)

#         self.bm25 = BM25Okapi(self.tokenized)

#     def search(self, query, k=5):
#         tokens = query.lower().split()
#         scores = self.bm25.get_scores(tokens)

#         ranked = sorted(
#             zip(self.docs, scores),
#             key=lambda x: x[1],
#             reverse=True
#         )

#         return [
#             {
#                 "text": doc["text"],
#                 "score": score,
#                 # "source": doc.get("source"),
#                 "href": doc.get("href")
#             }
#             for doc, score in ranked[:k]
#         ]


# def bs4_extractor(html: str):
#     soup = BeautifulSoup(html, "lxml")

#     # ❌ Remove unwanted tags
#     for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
#         tag.decompose()

#     elements = soup.find_all(["h1", "h2", "h3", "p", "a", "li", "input"])

#     results = []

#     for el in elements:
#         text = el.get_text(separator=" ", strip=True)

#         # ❌ Skip empty
#         if not text:
#             continue

#         # ❌ Normalize whitespace
#         text = re.sub(r"[ \t]+", " ", text)

#         # ❌ Skip UI labels
#         if text.lower() in {
#             "world news", "politics news", "view more", "in focus"
#         }:
#             continue

#         # ❌ Skip timestamps
#         if re.search(r"\b\d{1,2}:\d{2}\s?(AM|PM)\b", text):
#             continue

#         # ❌ Skip dates
#         if re.search(r"\b[A-Za-z]+\s\d{1,2},\s\d{4}\b", text):
#             continue

#         # ❌ Skip short junk
#         if len(text) < 40:
#             continue

#         result = {
#             "text": text,
#             "tag": el.name,
#             "id": el.get("id"),
#             "name": el.get("name"),
#             "href": el.get("href") if el.name == "a" else None
#         }

#         results.append(result)

#     return json.dumps(results)


# from urllib.parse import urlparse

# def get_base_url(url: str) -> str:
#     parsed = urlparse(url)
#     return f"{parsed.scheme}://{parsed.netloc}"

# # @tool
# async def scrape_url(url: str, query: str):

#     def is_error_page(doc):
#         text = doc.page_content.lower()
#         return (
#             "an error occurred" in text or
#             "reference #" in text or
#             "edgesuite.net" in text
#         )

#     def fix_url(url: str) -> str:
#         if not url:
#             return url
#         if "http" in url[8:]:
#             return url[url.find("http", 8):]
#         return url

#     loader = RecursiveUrlLoader(
#         url,
#         extractor=bs4_extractor,  # returns JSON string
#         use_async=True,
#         max_depth=3,  # 🔥 reduce depth (5 is too aggressive)
#         headers={
#             "User-Agent": "Mozilla/5.0",
#             "Accept": "text/html"
#         },
#         prevent_outside=True,
#         base_url=get_base_url(url)
#     )

#     documents = []

#     async for doc in loader.alazy_load():

#         source = fix_url(doc.metadata.get("source"))

#         if not source.startswith("http"):
#             continue

#         if is_error_page(doc):
#             continue

#         try:
#             # ✅ parse JSON from extractor
#             structured = json.loads(doc.page_content)
#         except:
#             continue

#         for item in structured:
#             text = item.get("text", "").strip()

#             if not text or len(text) < 40:
#                 continue

#             documents.append({
#                 "text": text,
#                 "source": source,
#                 "tag": item.get("tag"),
#                 "href": item.get("href")
#             })

#     # ✅ Deduplicate
#     seen = set()
#     unique_docs = []

#     for doc in documents:
#         if doc["text"] in seen:
#             continue
#         seen.add(doc["text"])
#         unique_docs.append(doc)
#     print(documents)
#     # ✅ BM25
#     bm25 = BM25Index()
#     bm25.add_documents(unique_docs)

#     return bm25.search(query, k=5)


# import asyncio

# print(asyncio.run(scrape_url("https://moneycontrol.com", "multibagger stocks")))