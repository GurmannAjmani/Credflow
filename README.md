# About the company:
### Industry: Fintech
Digital lending platform that provides short term working capital/loans to individuals, small and medium businesses. It uses AI powered risk scoring to approve loans within 24 hours by analyzing GST data, bank statements and transaction histories.
# AI Questionnaire Automation

This is a Flask-based Retrieval-Augmented Generation (RAG) application designed to automate the process of answering complex questionnaires based on a provided knowledge base.

## 1. What I Built
- **End-to-End RAG Pipeline**: Integrated LangChain with Google Gemini APIs and FAISS to ingest PDF/CSV documents and provide cited answers.
- **Automated Extraction**: Regex-based parser to automatically detect and extract structured questions from uploaded PDF questionnaires.
- **Secure Multi-Tenancy**: A robust user authentication system where each user has private storage and a personal history of runs.
- **Export & Reporting**: Automated PDF generation for results, including snippets and citations, allowing for easy sharing and auditing.
- **Interactive Dashboard**: A workspace to manage past runs, view results, and regenerate specific answers.

## 2. Assumptions
- **Question Formatting**: Assumed questions in the PDF follow a standard `Q1. Question text` or similar numbered format for regex extraction.
- **Document Quality**: Assumed that the uploaded knowledge base PDFs are text-searchable (not scanned images without OCR).

## 3. Trade-offs
- **LLM vs. Local BERT**: Initially experimented with a small BERT-based model for extraction and QA. While it offered higher accuracy for specific domain-related terminology, it was extremely heavy and slow to run on local CPU/GPU hardware. Switched to Gemini Flash to provide a responsive, real-time user experience while maintaining high reasoning quality.
- **Batch Processing (4 Questions/Call)**: Implemented batching of 4 questions per API call. This was a necessary trade-off to navigate API rate limits and optimize speed; however, increasing the batch size beyond this point resulted in a noticeable drop in accuracy per answer as the model's focus was spread too thin across multiple contexts.

## 4. Future Improvements
- **Elaborate Vector Database**: Transition from FAISS to a more robust, production-grade vector database (e.g., Qdrant, Milvus, or Pinecone). This would allow for more precise indexing, metadata filtering, and advanced querying capabilities to drive higher answer accuracy.
- **Semantic Similarity Search**: Upgrade the retrieval engine to use more advanced semantic similarity techniques to ensure the AI finds even deeper connections between the questions and the knowledge base.
- **Confidence Scoring**: Implement a scoring system that quantifies the AI's confidence in each answer, flagging low-confidence results for manual human review.
- **OCR Integration**: Add Tesseract or AWS Textract to handle scanned PDFs and images.
- **Background Tasks**: Move the heavy AI processing to a Celery/Redis worker queue to prevent frontend timeouts during large document processing.
- **Human-in-the-Loop**: Add an interface for users to manually edit/correct AI answers before exporting the final PDF.
