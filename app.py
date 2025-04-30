from flask import Flask, render_template, request, redirect, url_for, flash, session
import psycopg2
from werkzeug.utils import secure_filename
import os
import uuid
from functools import wraps
from collections import Counter
from db import (
    fetch_all_users, fetch_documents, insert_document, fetch_library,
    insert_transaction, fetch_user_balance, update_user_balance,
    get_document_by_id, get_author_documents, register_purchase,
    get_user_by_id, authenticate_user, register_user, user_exists
)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configuración
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Decorador login_required con wraps
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para acceder a esta página')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Funciones auxiliares
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rutas
@app.route('/')
def index():
    documents = fetch_documents(3)
    return render_template('index.html', documents=documents)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        usuarioId = request.form.get('usuarioId')
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        role = request.form.get('role', 'comprador')

        # Validaciones básicas
        if not all([usuarioId, username, password, email]):
            flash('Todos los campos son obligatorios', 'error')
            return redirect(url_for('register'))

        if user_exists(usuarioId):
            flash('El usuario ya existe', 'error')
            return redirect(url_for('register'))

        if register_user(usuarioId, username, password, email, role):
            flash('Registro exitoso! Por favor inicia sesión', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error en el registro', 'error')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = authenticate_user(email, password)
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]
            flash(f'Bienvenido {user[1]}!')
            return redirect(url_for('index'))
        flash('Credenciales incorrectas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente')
    return redirect(url_for('index'))

@app.route('/publish', methods=['GET', 'POST'])
@login_required
def publish_document():
    if session.get('role') != 'vendedor':
        flash('Solo los vendedores pueden publicar documentos')
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
            
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            if os.path.getsize(filepath) > 10*1024*1024:
                os.remove(filepath)
                flash('El archivo es demasiado grande (máximo 10MB)')
                return redirect(request.url)
            
            doc_id = str(uuid.uuid4()).replace('-', '')[:20]
            insert_document(
                doc_id=doc_id,
                title=request.form.get('title'),
                description=request.form.get('description', ''),
                file_path=filename,
                price=float(request.form.get('price')),
                category=request.form.get('category'),
                author_id=session['user_id'],
                pages=request.form.get('pages', 0)
            )
            flash('Documento publicado con éxito!')
            return redirect(url_for('index'))
    
    return render_template('publish.html')

@app.route('/browse')
def browse_documents():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    conn = get_db_connection()
    conn.set_client_encoding('UTF8')  # 🔹 Asegura que los datos se interpreten correctamente
    cur = conn.cursor()
    
    # Consulta SQL con parámetros dinámicos para evitar SQL Injection
    sql = """
    SELECT d.documentoId, d.titulo, d.precio, d.categoria, d.rutaArchivo, u.nombre as autor
    FROM documentos d
    JOIN usuarios u ON d.autorId = u.usuarioId
    WHERE 1=1
    """
    params = []

    if query:
        sql += " AND d.titulo ILIKE %s"
        params.append(f'%{query}%')
    if category:
        sql += " AND d.categoria = %s"
        params.append(category)

    cur.execute(sql, params)
    
    # Convertir los resultados en un formato adecuado para Flask
    documents = [
        {
            "id": row[0],
            "title": row[1],
            "price": row[2],
            "category": row[3],
            "file_path": row[4],
            "author": row[5]
        }
        for row in cur.fetchall()
    ]
    
    cur.close()
    conn.close()
    
    return render_template('browse.html', documents=documents, query=query, category=category)

@app.route('/document/<doc_id>')
def view_document(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado')
        return redirect(url_for('browse_documents'))

    author = get_user_by_id(doc[6])  # Verifica que doc[6] sea el ID del autor
    users = fetch_all_users()
    return render_template('document.html', document={
        'id': doc[0], 'title': doc[1], 'description': doc[2],
        'file': doc[3], 'price': doc[4], 'category': doc[5],
        'author': author[1] if author else 'Desconocido',
        'verified': doc[7], 'upload_date': doc[8], 'pages': doc[9]
        }, users=users)

@app.route('/payment/<doc_id>', methods=['GET', 'POST'])
@login_required
def process_payment(doc_id):
    if session.get('role') != 'comprador':
        flash('Solo los compradores pueden acceder a esta página')
        return redirect(url_for('index'))
    
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado')
        return redirect(url_for('browse_documents'))
    
    if request.method == 'POST':
        card_number = request.form.get('card_number')
        if not card_number or len(card_number.replace(' ', '')) != 16:
            flash('Número de tarjeta inválido')
            return redirect(request.url)
        
        amount = doc[4]
        royalty = amount * 0.7
        
        insert_transaction(
            doc_id=doc_id,
            buyer_id=session['user_id'],
            amount=amount,
            royalty=royalty,
            payment_method='tarjeta'
        )
        
        update_user_balance(doc[6], fetch_user_balance(doc[6]) + royalty)
        register_purchase(session['user_id'], doc_id)
        
        flash('Compra exitosa! El documento ha sido añadido a tu biblioteca.')
        return redirect(url_for('view_library'))
    
    return render_template('payment.html', document={
        'id': doc[0], 'title': doc[1], 'price': doc[4]
    })

@app.route('/library')
@login_required
def view_library():
    if session.get('role') != 'comprador':
        flash('Solo los compradores pueden acceder a la biblioteca')
        return redirect(url_for('index'))
    return render_template('library.html', purchases=fetch_library(session['user_id']))

@app.route('/dashboard')
@login_required
def author_dashboard():
    if session.get('role') != 'vendedor':
        flash('Solo los vendedores pueden acceder al panel de control')
        return redirect(url_for('index'))
        
    author_docs = get_author_documents(session['user_id'])
    total_earnings = 0
    formatted_docs = []
    
    for doc in author_docs:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT SUM(regalia) FROM transacciones WHERE documentoId = %s", (doc[0],))
        earnings = cur.fetchone()[0] or 0
        cur.close()
        conn.close()
        
        total_earnings += earnings
        formatted_docs.append({
            'id': doc[0], 'title': doc[1], 'price': doc[4],
            'category': doc[5], 'earnings': earnings
        })
    
    return render_template('author_dashboard.html',
        documents=formatted_docs,
        balance=fetch_user_balance(session['user_id']),
        total_earnings=total_earnings
    )

# Función de conexión a la base de datos
def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="bdEducApp",
        user="postgres",
        password = "@Uc19072004e".encode('ascii', 'ignore').decode('ascii'),  # Cambiar por tu contraseña
        client_encoding='utf8'  # Fuerza la codificación UTF-8
    )

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)