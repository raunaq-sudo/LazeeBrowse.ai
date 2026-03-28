import os
from dotenv import load_dotenv
load_dotenv()

GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

from langchain_google_genai import ChatGoogleGenerativeAI
llm_sys_prmpt_gen_ = ChatGoogleGenerativeAI(
    model="gemini-3.1-pro-preview",
    temperature=0.4,  # Gemini 3.0+ defaults to 1.0
    api_key=os.getenv("GEMINI_API_KEY"),
    # other params...
)
llm_ = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    temperature=0.4,  # Gemini 3.0+ defaults to 1.0
    api_key=os.getenv("GEMINI_API_KEY"),
    # other params...
)

from langchain_deepseek import ChatDeepSeek

llm = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0.4,
    max_tokens=None,
    timeout=None,
    max_retries=2
)

llm_sys_prmpt_gen = ChatDeepSeek(
    model="deepseek-chat",
    temperature=0.4,
    max_tokens=None,
    timeout=None,
    max_retries=2
)