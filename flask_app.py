from flask import Flask, render_template, request, session, redirect, url_for, jsonify, send_file
import os
import re
import json
import bcrypt
import uuid
from datetime import datetime
from dotenv import load_dotenv
from functools import wraps
from fpdf import FPDF
import io

from database import (
    init_db,
    create_user,
    get_user,
    save_answers,
    save_run,
    get_user_history,
    update_run_pdf
)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
load_dotenv()
init_db()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
os.makedirs("storage", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, google_api_key=GEMINI_API_KEY)
embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001", google_api_key=GEMINI_API_KEY)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def safe_text(text):
    return text.encode('latin-1', 'replace').decode('latin-1')

def parse_questions(text):
    pattern = r"(Q\d+\..*?)(?=Q\d+\.|$)"
    matches = re.findall(pattern, text, re.DOTALL)
    return [q.strip() for q in matches]

def get_qa_response(query_text, retriever_obj):
    retrieved_docs = retriever_obj.invoke(query_text)
    context_text = "\n\n".join([f"(Source: {doc.metadata.get('source','')})\n{doc.page_content}" for doc in retrieved_docs])
    
    prompt = f"""Return ONLY valid JSON. Do NOT wrap in markdown. Do NOT include explanations.
Format strictly:
[
 {{
   "question": "...",
   "answer": "...",
   "citation": "ONLY one filename",
   "snippet": "Short extract from source (max 350 chars)"
 }}
]
Rules: Use ONLY context. If not found, answer = "Not Found in References", citation = "N/A", snippet = "N/A"
Context: {context_text}
Questions: {query_text}"""
    
    response = llm.invoke(prompt)
    raw = response.content.strip()
    raw = re.sub(r"^```json", "", raw)
    raw = re.sub(r"^```", "", raw)
    raw = re.sub(r"```$", "", raw).strip()
    
    try:
        data = json.loads(raw)
        for item in data:
            cit = item.get("citation", "").strip()
            if "," in cit:
                cit = cit.split(",")[0].strip()
            item["citation"] = cit.replace('"', '')
        return data
    except:
        return None
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not username or not password:
            return render_template('register.html', error="Username and password required")

        if get_user(username):
            return render_template('register.html', error="Username already exists")

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        create_user(username, name, email, hashed)
        os.makedirs(f"storage/{username}", exist_ok=True)
        
        return render_template('register.html', success="Account created! Please login.")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = get_user(username)
        if user and bcrypt.checkpw(password.encode(), user[4].encode()):
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    username = session['user']
    history = get_user_history(username)
    return render_template('dashboard.html', username=username, history=history)

@app.route('/api/process', methods=['POST'])
@login_required
def api_process():
    username = session['user']
    USER_DIR = f"storage/{username}"
    FAISS_DIR = f"{USER_DIR}/faiss_index"
    os.makedirs(USER_DIR, exist_ok=True)

    if 'kb_files' not in request.files or 'question_file' not in request.files:
        return jsonify({'error': 'Missing files'}), 400

    kb_files = request.files.getlist('kb_files')
    question_file = request.files['question_file']

    if not kb_files or not question_file:
        return jsonify({'error': 'Please upload both knowledge base and questionnaire'}), 400

    try:
        documents = []
        for file in kb_files:
            filepath = os.path.join(USER_DIR, file.filename)
            file.save(filepath)
            
            if file.filename.endswith('.pdf'):
                loader = PyPDFLoader(filepath)
            else:
                loader = CSVLoader(filepath)
            
            loaded_docs = loader.load()
            for doc in loaded_docs:
                doc.metadata["source"] = file.filename
            documents.extend(loaded_docs)

        splitter = RecursiveCharacterTextSplitter(chunk_size=3500, chunk_overlap=500)
        docs = splitter.split_documents(documents)
        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(FAISS_DIR)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 8})
        q_path = os.path.join(USER_DIR, question_file.filename)
        question_file.save(q_path)
        q_loader = PyPDFLoader(q_path)
        q_docs = q_loader.load()
        question_text = "\n".join([doc.page_content for doc in q_docs])
        questions = parse_questions(question_text)

        if not questions:
            return jsonify({'error': 'No questions detected'}), 400
        all_answers = []
        BATCH_SIZE = 4
        
        for i in range(0, len(questions), BATCH_SIZE):
            batch = questions[i:i+BATCH_SIZE]
            combined_query = "\n".join(batch)
            result = get_qa_response(combined_query, retriever)
            if result:
                all_answers.extend(result)
        run_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_filename = f"{USER_DIR}/output_{timestamp}.txt"
        with open(raw_filename, "w", encoding="utf-8") as f:
            f.write(json.dumps(all_answers, indent=2))

        save_run(username, run_id, raw_filename)
        save_answers(username, run_id, all_answers)

        return jsonify({
            'success': True,
            'answers': all_answers,
            'total': len(all_answers),
            'found': sum(1 for item in all_answers if item["answer"] != "Not Found in References"),
            'run_id': run_id
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/regenerate/<int:idx>', methods=['POST'])
@login_required
def api_regenerate(idx):
    username = session['user']
    USER_DIR = f"storage/{username}"
    FAISS_DIR = f"{USER_DIR}/faiss_index"

    data = request.json
    question = data.get('question')

    try:
        vectorstore = FAISS.load_local(FAISS_DIR, embeddings, allow_dangerous_deserialization=True)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 8})
        new_data = get_qa_response(question, retriever)
        
        if new_data:
            return jsonify({'success': True, 'answer': new_data[0]})
        else:
            return jsonify({'error': 'Failed to regenerate'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-pdf', methods=['POST'])
@login_required
def api_export_pdf():
    username = session['user']
    USER_DIR = f"storage/{username}"
    os.makedirs(USER_DIR, exist_ok=True)
    
    data = request.json
    export_data = data.get('answers', [])
    run_id = data.get('run_id')

    if not export_data:
        return jsonify({'error': 'No data to export'}), 400

    try:
        found_q = sum(1 for item in export_data if item["answer"] != "Not Found in References")
        not_found_q = len(export_data) - found_q

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Title
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, "CredFlow QA Export", ln=True, align='C')
        pdf.ln(10)

        # Summary
        pdf.set_font("Arial", '', 12)
        pdf.multi_cell(0, 8, f"Summary:\nTotal Questions: {len(export_data)}\nAnswered (with Citations): {found_q}\nNot Found: {not_found_q}")
        pdf.ln(8)

        # Questions & Answers
        for idx, item in enumerate(export_data, start=1):
            pdf.set_font("Arial", 'B', 14)
            pdf.multi_cell(0, 8, safe_text(f"{idx}. {item['question']}"))

            pdf.set_font("Arial", '', 12)
            pdf.multi_cell(0, 8, safe_text(f"A: {item['answer']}"))

            pdf.set_font("Arial", 'B', 11)
            pdf.multi_cell(0, 8, safe_text(f"Citation: {item['citation']}"))

            pdf.set_font("Arial", 'I', 11)
            pdf.multi_cell(0, 8, safe_text(f"Snippet: {item['snippet']}"))

            pdf.ln(5)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        pdf_filename = f"{USER_DIR}/export_{timestamp}.pdf"
        pdf.output(pdf_filename)
        if run_id:
            update_run_pdf(run_id, pdf_filename)

        return send_file(
            pdf_filename,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"export_{timestamp}.pdf"
        )
    
    except Exception as e:
        return jsonify({'error': f'PDF export failed: {str(e)}'}), 500


@app.route('/api/download-pdf/<run_id>', methods=['GET'])
@login_required
def api_download_pdf(run_id):
    """Download a previously generated PDF from a run."""
    username = session['user']
    
    try:
        conn = __import__('sqlite3').connect('credflow.db')
        c = conn.cursor()
        c.execute("""
        SELECT pdf_output_file FROM runs
        WHERE run_id = ? AND username = ?
        """, (run_id, username))
        
        result = c.fetchone()
        conn.close()
        
        if not result or not result[0]:
            return jsonify({'error': 'PDF not found'}), 404
        
        pdf_path = result[0]
        
        if not os.path.exists(pdf_path) or not pdf_path.startswith(f"storage/{username}"):
            return jsonify({'error': 'PDF file not found'}), 404
        
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=os.path.basename(pdf_path)
        )
    
    except Exception as e:
        return jsonify({'error': f'Download failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
