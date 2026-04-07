import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# -------------------------------
# Config
# -------------------------------
INDEX_TEXT = "faiss_text.index"
TEXTS_TEXT = "texts_text.npy"

INDEX_SEM = "faiss_semantic.index"
TEXTS_SEM = "texts_semantic.npy"

MODEL_PATH = "./models/all-MiniLM-L6-v2"

# -------------------------------
# Load model
# -------------------------------
model = SentenceTransformer(MODEL_PATH, trust_remote_code=True)

# -------------------------------
# Helpers
# -------------------------------
def normalize(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / norms

def load_index(path, dim):
    if os.path.exists(path):
        return faiss.read_index(path)
    return faiss.IndexFlatIP(dim)

def save_index(index, path):
    faiss.write_index(index, path)

def load_store(path):
    if os.path.exists(path):
        return list(np.load(path, allow_pickle=True))
    return []

def save_store(data, path):
    np.save(path, np.array(data, dtype=object))

# -------------------------------
# Chunking
# -------------------------------
def chunk_text(text, chunk_size=20, overlap=5):
    words = text.split()
    return [
        " ".join(words[i:i + chunk_size])
        for i in range(0, len(words), chunk_size - overlap)
        if words[i:i + chunk_size]
    ]

# -------------------------------
# Rebuild Index
# -------------------------------
def rebuild_index(texts, index_path):
    if not texts:
        if os.path.exists(index_path):
            os.remove(index_path)
        return

    embeddings = model.encode(texts)
    embeddings = normalize(np.array(embeddings).astype("float32"))

    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)

    save_index(index, index_path)

# -------------------------------
# ADD → CONTENT STORE
# -------------------------------
def add_content(doc_name, url, last_updated, content):
    chunks = chunk_text(content)

    texts = [
        f"{doc_name} || {url} || {last_updated} || {chunk}"
        for chunk in chunks
    ]

    if not texts:
        return

    embeddings = normalize(np.array(model.encode(texts)).astype("float32"))

    index = load_index("./embeddings/" + doc_name + "_text.index", embeddings.shape[1])
    store = load_store("./embeddings/" + doc_name + "_text.npy")

    if index.ntotal != len(store):
        raise ValueError("TEXT store mismatch")

    index.add(embeddings)
    store.extend(texts)

    save_index(index, "./embeddings/" + doc_name + "_text.index")
    save_store(store, "./embeddings/" + doc_name + "_text.npy")

    print(f"📄 Content added: {doc_name}")

# -------------------------------
# ADD → SEMANTIC STORE
# -------------------------------
def add_semantic(doc_name, url, last_updated, html):

    print("adding semantics")
    chunks = chunk_text(html, 100, 20)
    texts = [
        f"{doc_name} || {url} || {last_updated} || {chunk}"
        for chunk in chunks
    ]

    if not texts:
        return

    embeddings = normalize(np.array(model.encode(texts)).astype("float32"))

    index = load_index("./embeddings/" + doc_name + "_semantic.index", embeddings.shape[1])
    store = load_store("./embeddings/" + doc_name + "_semantic.npy")

    if index.ntotal != len(store):
        raise ValueError("SEMANTIC store mismatch")

    index.add(embeddings)
    store.extend(texts)
    print("Saving index and store.")
    save_index(index, "./embeddings/" + doc_name + "_semantic.index")
    save_store(store, "./embeddings/" + doc_name + "_semantic.npy")

    print(f"🧠 Semantic added: {doc_name}")

# -------------------------------
# SEARCH → CONTENT
# -------------------------------
def search_content(query, doc_name, top_k=30):
    if not os.path.exists("./embeddings/" + doc_name + "_text.index"):
        return []

    index = faiss.read_index("./embeddings/" + doc_name + "_text.index")
    store = load_store("./embeddings/" + doc_name + "_text.npy")

    q = normalize(np.array(model.encode([query])).astype("float32"))

    _, idxs = index.search(q, top_k)

    return [store[i] for i in idxs[0] if i != -1 and i < len(store)]

# -------------------------------
# SEARCH → SEMANTIC
# -------------------------------
def search_semantic(query, doc_name, top_k=2):
    if not os.path.exists("./embeddings/" + doc_name + "_semantic.index"):
        return []

    index = faiss.read_index("./embeddings/" + doc_name + "_semantic.index")
    store = load_store("./embeddings/" + doc_name + "_semantic.npy")

    q = normalize(np.array(model.encode([query])).astype("float32"))

    _, idxs = index.search(q, top_k)

    return [store[i] for i in idxs[0] if i != -1 and i < len(store)]

# -------------------------------
# SEARCH → COMBINED
# -------------------------------
def search_all(query, doc_name):
    return {
        "semantic": search_semantic(query, doc_name),
        "content": search_content(query, doc_name)
    }

# -------------------------------
# REMOVE DOCUMENT (BOTH STORES)
# -------------------------------
def remove_document(doc_name):
    # TEXT STORE
    text_store = load_store(TEXTS_TEXT)
    text_filtered = [t for t in text_store if not t.startswith(f"{doc_name} ||")]
    save_store(text_filtered, TEXTS_TEXT)
    rebuild_index(text_filtered, INDEX_TEXT)

    # SEMANTIC STORE
    sem_store = load_store(TEXTS_SEM)
    sem_filtered = [t for t in sem_store if not t.startswith(f"{doc_name} ||")]
    save_store(sem_filtered, TEXTS_SEM)
    rebuild_index(sem_filtered, INDEX_SEM)

    print(f"🗑️ Removed document: {doc_name}")

# -------------------------------
# CLEAR STORAGE
# -------------------------------
def clear_storage(doc_name):
    for f in ["./embeddings/" + doc_name + "_semantic.index",
              "./embeddings/" + doc_name + "_semantic.npy",
              "./embeddings/" + doc_name + "_text.index",
              "./embeddings/" + doc_name + "_text.npy"]:
        if os.path.exists(f):
            os.remove(f)
    print("🗑️ Cleared all storage")

# -------------------------------
# Example Usage
# -------------------------------
if __name__ == "__main__":
    clear_storage()

    # Add content
    add_content(
        "Login Page",
        "https://example.com/login","",
        "Click the login button to sign in. Enter email and password."
    )

    # Add semantic UI
    add_semantic(
        "Login Page",
        "https://example.com/login","",
        [
            {"tag": "button", "text": "Login", "id": "login-btn"},
            {"tag": "input", "placeholder": "Email"},
            {"tag": "input", "placeholder": "Password"}
        ]
    )

    print("\n🔍 Search (combined):")
    print(search_all("login button"))

    print("\n🗑️ Removing Login Page...")
    remove_document("Login Page")

    print("\n🔍 After delete:")
    print(search_all("login button"))