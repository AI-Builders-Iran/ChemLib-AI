from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=r"D:\AI_Biulders_iran_Team\DocumentAI\.env")

from src.loaders.pdf_loader import PDFLoader

docs = PDFLoader().load(file=r"C:\Users\hosse\Downloads\test2.pdf")
for i, doc in enumerate(docs):
    print(f"--- صفحه {i} ---")
    print(doc.page_content)
