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

# Decoradores
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para acceder a esta página')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def vendor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'vendedor':
            flash('Acceso restringido a vendedores')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def buyer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'comprador':
            flash('Acceso restringido a compradores')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Funciones auxiliares
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="bdEducApp",
        user="postgres",
        password="@Uc19072004e".encode('ascii', 'ignore').decode('ascii'),
        client_encoding='utf8'
    )

###############################################################################
# Rutas Públicas
###############################################################################

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
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = authenticate_user(email, password)
        if user:
            session['user_id'] = user[0]  # usuarioId
            session['username'] = user[1]  # nombre
            session['role'] = user[2]  # rol
            session['email'] = email
            flash(f'Bienvenido {user[1]}!')
            
            if user[2] == 'vendedor':
                return redirect(url_for('vendor_dashboard'))
            else:
                return redirect(url_for('browse_documents'))
                
        flash('Credenciales incorrectas')
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión correctamente')
    return redirect(url_for('index'))

@app.route('/browse')
def browse_documents():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    conn = get_db_connection()
    conn.set_client_encoding('UTF8')
    cur = conn.cursor()
    
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

    author = get_user_by_id(doc[6])
    users = fetch_all_users()
    return render_template('document.html', document={
        'id': doc[0], 'title': doc[1], 'description': doc[2],
        'file': doc[3], 'price': doc[4], 'category': doc[5],
        'author': author[1] if author else 'Desconocido',
        'verified': doc[7], 'upload_date': doc[8], 'pages': doc[9]
        }, users=users)

###############################################################################
# Rutas del Comprador
###############################################################################

@app.route('/payment/<doc_id>', methods=['GET', 'POST'])
@login_required
@buyer_required
def process_payment(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado')
        return redirect(url_for('browse_documents'))
    
    # Verificar si ya lo compró
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM bibliotecas 
        WHERE usuarioId = %s AND documentoId = %s
        """, (session['user_id'], doc_id))
    if cur.fetchone():
        flash('Ya has comprado este documento')
        return redirect(url_for('view_library'))
    cur.close()
    conn.close()
    
    if request.method == 'POST':
        # Simulación de validación de tarjeta
        card_number = request.form.get('card_number', '').replace(' ', '')
        if len(card_number) != 16 or not card_number.isdigit():
            flash('Número de tarjeta inválido', 'error')
            return redirect(request.url)
        
        amount = doc[4]
        royalty = amount * 0.7  # 70% para el autor
        
        # Registrar transacción
        insert_transaction(
            doc_id=doc_id,
            buyer_id=session['user_id'],
            amount=amount,
            royalty=royalty,
            payment_method='tarjeta'
        )
        
        # Actualizar saldo del autor
        update_user_balance(doc[6], fetch_user_balance(doc[6]) + royalty)
        
        # Registrar compra en biblioteca
        register_purchase(session['user_id'], doc_id)
        
        flash('Compra exitosa! El documento ha sido añadido a tu biblioteca.', 'success')
        return redirect(url_for('view_document', doc_id=doc_id))
    
    return render_template('payment.html', 
        document={
            'id': doc[0], 
            'title': doc[1], 
            'price': doc[4],
            'author': get_user_by_id(doc[6])[1]
        }
    )

@app.route('/library')
@login_required
@buyer_required
def view_library():
    purchases = fetch_library(session['user_id'])
    
    # Organizar por categoría
    categories = {}
    for doc in purchases:
        if doc[2] not in categories:
            categories[doc[2]] = []
        categories[doc[2]].append(doc)
    
    return render_template('library.html', 
        categories=categories,
        total=len(purchases)
    )

###############################################################################
# Rutas del Vendedor
###############################################################################

@app.route('/vendor/dashboard')
@login_required
@vendor_required
def vendor_dashboard():
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
            'category': doc[5], 'earnings': earnings,
            'sales': len(get_document_sales(doc[0]))  # Función ficticia - implementar
        })
    
    return render_template('vendor/dashboard.html',
        documents=formatted_docs,
        balance=fetch_user_balance(session['user_id']),
        total_earnings=total_earnings
    )

@app.route('/vendor/documents')
@login_required
@vendor_required
def vendor_documents():
    documents = get_author_documents(session['user_id'])
    return render_template('vendor/documents.html', documents=documents)

@app.route('/vendor/publish', methods=['GET', 'POST'])
@login_required
@vendor_required
def publish_document():
    if request.method == 'POST':
        title = request.form.get('title')
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM documentos WHERE titulo = %s", (title,))
        if cur.fetchone():
            flash('Ya existe un documento con ese título. Por favor elige otro.', 'error')
            return redirect(request.url)
        
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(request.url)
            
        if not allowed_file(file.filename):
            flash('Tipo de archivo no permitido', 'error')
            return redirect(request.url)
            
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        if os.path.getsize(filepath) > 10*1024*1024:
            os.remove(filepath)
            flash('El archivo es demasiado grande (máximo 10MB)', 'error')
            return redirect(request.url)
        
        pages = request.form.get('pages', 0)
        try:
            pages = int(pages)
        except:
            pages = 0
            
        price = float(request.form.get('price', 0))
        if price < 1 or price > 100:
            flash('El precio debe estar entre $1 y $100', 'error')
            return redirect(request.url)
        
        doc_id = str(uuid.uuid4()).replace('-', '')[:20]
        insert_document(
            doc_id=doc_id,
            title=title,
            description=request.form.get('description', ''),
            file_path=filename,
            price=price,
            category=request.form.get('category'),
            author_id=session['user_id'],
            pages=pages
        )
        
        flash('Documento publicado con éxito!', 'success')
        return redirect(url_for('vendor_dashboard'))
    
    return render_template('vendor/publish.html', 
        categories=['Matemáticas', 'Física', 'Química', 'Literatura', 'Historia']
    )

@app.route('/vendor/withdraw', methods=['GET', 'POST'])
@login_required
@vendor_required
def withdraw_funds():
    balance = fetch_user_balance(session['user_id'])
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        
        if amount <= 0:
            flash('El monto debe ser positivo', 'error')
        elif amount > balance:
            flash('Fondos insuficientes', 'error')
        else:
            # Registrar retiro
            update_user_balance(session['user_id'], balance - amount)
            flash(f'Retiro de ${amount:.2f} procesado exitosamente', 'success')
            return redirect(url_for('vendor_dashboard'))
    
    return render_template('vendor/withdraw.html', balance=balance)

###############################################################################
# Inicialización
###############################################################################

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)