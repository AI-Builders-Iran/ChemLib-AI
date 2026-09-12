# 🤖 DocumentAI
## Production-Ready LLM Document Intelligence Pipeline

<p align="center">

Transform unstructured documents into reliable, structured, and validated data using modern LLM pipelines.

</p>

---

## 🚀 Overview

DocumentAI is an AI-powered document intelligence system designed to extract structured information from real-world documents such as invoices and contracts.

The system automatically:

- 📄 Loads documents (PDF / DOCX / TXT)
- 🧹 Cleans and normalizes text
- ✂️ Performs intelligent chunking
- 🧠 Uses Large Language Models for understanding
- ✅ Generates schema-validated JSON output
- 🚀 Provides production APIs and user interfaces

Unlike simple LLM applications that return raw text, DocumentAI produces reliable structured outputs suitable for integration into business workflows.

---

## 🎯 Business Problem

Organizations process thousands of documents every day:

- invoices
- contracts
- reports
- agreements

Manual extraction is:

❌ slow  
❌ expensive  
❌ error-prone  

DocumentAI automates this process by converting unstructured documents into machine-readable business data.

---

# ✨ Key Features

## 🧠 LLM-Powered Information Extraction

- Multi-provider LLM architecture
- Google Gemini as primary provider
- OpenRouter fallback mechanism
- Provider abstraction for future model expansion


## 📦 Structured Output Generation

Instead of returning unreliable raw text responses, DocumentAI generates validated structured outputs.

Powered by:

- ✅ **Pydantic Validation** — Ensures data correctness and schema compliance
- ✅ **Schema-Driven Extraction** — Uses predefined schemas for reliable information extraction
- ✅ **Type-Safe Responses** — Provides predictable and integration-ready outputs


```json
{
 "document_type": "invoice",
 "invoice_number": "INV-1024",
 "vendor": "ABC Company",
 "total": 12500000
}
```

---

# 🔄 End-to-End AI Pipeline

```text
Document (PDF / DOCX / TXT)
          |
          ↓
   Document Loader
          |
          ↓
   Text Processing
          |
          ↓
 Unicode Normalization
 Text Cleaning
 Recursive Chunking
          |
          ↓
 LLM Extraction Engine
          |
          ↓
 Structured JSON Output
          |
          ↓
 Validated Pydantic Model

```

---

## 🏗 Architecture

```text

                         PDF / DOCX / TXT

                                |
                                ↓

                      ┌─────────────────┐
                      │ Document Loader │
                      └────────┬────────┘

                               |
                               ↓

                 ┌────────────────────────┐
                 │ Text Processing Layer  │
                 ├────────────────────────┤
                 │ Unicode Normalization  │
                 │ Text Cleaning          │
                 │ Recursive Chunking     │
                 └───────────┬────────────┘

                               |
                               ↓

                 ┌────────────────────────┐
                 │ LLM Extraction Engine  │
                 ├────────────────────────┤
                 │ Google Gemini          │
                 │ OpenRouter Fallback    │
                 └───────────┬────────────┘

                               |
                               ↓

                 ┌────────────────────────┐
                 │ Structured Output      │
                 │ Pydantic Models        │
                 └───────────┬────────────┘

                               |
                 ┌─────────────┴─────────────┐
                 ↓                           ↓

            ┌──────────┐              ┌───────────┐
            │ FastAPI  │              │ Streamlit │
            │ Backend  │              │    UI     │
            └──────────┘              └───────────┘

```

---

## 🛠 Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| LLM Framework | LangChain |
| AI Models | Google Gemini, OpenRouter |
| API | FastAPI |
| UI | Streamlit |
| Data Validation | Pydantic v2 |
| Testing | Pytest |
| Deployment | Docker |

---

## 📂 Project Structure

```text

DocumentAI/

├── app/
│   ├── api/
│   └── streamlit_app/
├── src/
│   ├── loaders/
│   │   └── PDF/DOCX/TXT processing
│   ├── processing/
│   │   ├── cleaners
│   │   └── chunking
│   ├── extraction/
│   │   ├── prompts
│   │   ├── providers
│   │   └── extractor
│   ├── schemas/
│   │   └── Structured models
│   └── pipeline/
│       └── End-to-end orchestration
├── tests/
├── Dockerfile
└── README.md

```

---

## ⚡ Quick Start

```bash
git clone <repository-url>

cd DocumentAI

python -m venv .venv

pip install -r requirements.txt
```

---

## 🔑 Configuration

```bash
export GEMINI_API_KEY="your-key"

# optional fallback

export OPENROUTER_API_KEY="your-key"
```

---

## 🚀 Usage

```python
result = pipeline.run(
    "invoice.pdf",
    DocumentType.INVOICE
)

print(result)
```

### REST API

Run:

```bash
uvicorn app.api.api_app:app --reload
```

Swagger:

```bash
http://localhost:8000/docs
```

### Streamlit Demo

```bash
streamlit run app/streamlit_app/app.py
```

---

# 🚀 Vision & Roadmap

DocumentAI represents the first step toward building an intelligent document processing platform designed to transform unstructured information into data that is usable, reliable, and processable by software systems.

Moving forward, the project will focus on building an Enterprise AI system capable of intelligently understanding, searching, analyzing, and making decisions based on documents.

Future development goals:

- 🧠 **Large Language Models (LLMs)**
- Enhancing capabilities for understanding and extracting information from complex documents
- Supporting various language models and local models


- 🔎 **Retrieval-Augmented Generation (RAG)**
- Creating an intelligent search system across document collections
- Generating responses based on organizational knowledge
- Reducing language model errors by utilizing authoritative sources


- 🤖 **Agentic AI Workflows**
- Developing intelligent agents to perform multi-step tasks
- Automating the planning, analysis, and execution of document-related processes


- 🏢 **Enterprise Document Automation**
- Automating organizational processes
- Integrating with business and information management systems
- Providing scalable solutions for enterprises


DocumentAI's ultimate goal is to build a new generation of intelligent systems that act like expert assistants—capable of understanding and analyzing organizational documents to generate operational value.

---

# 👥 Developers

Created by the **AI Builders** team

> We Don't Compete. We Replace.

| Engineer | Responsibility |
|----------|----------------|
| [![Hossein Heydari](https://github.com/HosseinHeydari2004.png)](https://github.com/HosseinHeydari2004) | Document Loading, Processing Pipeline |
| [![Nastaranyavari](https://github.com/Nastaranyavari.png)](https://github.com/Nastaranyavari) | LLM Extraction, Schemas |
| [![behrad](https://github.com/behradtbr.png)]([https://github.com/Nastaranyavari](https://github.com/behradtbr)) | Pipeline Integration, Testing |

---

## 📄 License

MIT License
