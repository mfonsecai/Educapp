from flask import send_file, send_from_directory, Flask, render_template, request, redirect, url_for, flash, session
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta
from decimal import Decimal
import psycopg2
from werkzeug.utils import secure_filename
import os
import uuid
import fitz
from functools import wraps
from collections import Counter
from flask_login import LoginManager, current_user
from db import (
    fetch_all_users, fetch_documents, insert_document, fetch_library,
    insert_transaction, fetch_user_balance, update_user_balance,
    get_document_by_id, get_author_documents, register_purchase,
    get_user_by_id, authenticate_user, register_user, user_exists, get_document_sales, get_document_sales_count,
    get_document_earnings,get_total_spent, get_recent_purchases, get_user_transactions,update_user_profile,check_purchase
)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configuración
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
csrf = CSRFProtect(app) 

login_manager = LoginManager()
login_manager.init_app(app)

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
def generate_secure_preview(doc_path):
    try:
        doc = fitz.open(f"static/uploads/{doc_path}")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=50)  # Baja resolución
        preview_path = f"static/previews/{secure_filename(doc_path)}_preview.jpg"
        pix.save(preview_path)
        return preview_path
    except Exception as e:
        print(f"Error generando preview: {e}")
        return None

# Funciones auxiliares
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="bdeducapp",
        user="postgres",
        password="1234".encode('ascii', 'ignore').decode('ascii'),
        client_encoding='utf8'
    )
# Modelo de usuario de ejemplo (debes adaptarlo a tu aplicación)
class User:
    def __init__(self, id, role='user'):
        self.id = id
        self.role = role
    
    def is_authenticated(self):
        return True
    
    def is_active(self):
        return True
    
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    # Aquí debes cargar el usuario real desde tu base de datos
    return User(user_id)


###############################################################################
# Rutas Públicas
###############################################################################

@app.route('/')
def index():
    documents_tuples = fetch_documents(3)
    documents = []
    for doc in documents_tuples:
        try:
            # Convierte explícitamente el precio a float
            price = float(doc[4]) if doc[4] is not None else 0.00
            author = get_user_by_id(doc[6]) if len(doc) > 6 and doc[6] else None
            
            documents.append({
                'id': doc[0],
                'title': doc[1],
                'price': price,
                'category': doc[5] if len(doc) > 5 else 'Sin categoría',
                'file_path': doc[3] if len(doc) > 3 else '',
                'author': author[1] if author else 'Desconocido'
            })
        except (IndexError, ValueError, TypeError) as e:
            print(f"Error procesando documento: {e}")
            continue
            
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
                return redirect(url_for('buyer_dashboard'))
                
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
            "price": float(row[2]),
            "category": row[3],
            "file_path": row[4],
            "author": row[5]
        }
        for row in cur.fetchall()
    ]
    
    cur.close()
    conn.close()
    
    return render_template('buyer/browse.html', 
                         documents=documents, 
                         query=query, 
                         category=category)
@app.route('/document/<doc_id>')
def view_document(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc:
        flash("Documento no encontrado", "error")
        return redirect(url_for('browse_documents'))

    purchased = 'user_id' in session and check_purchase(session['user_id'], doc_id)
    author = get_user_by_id(doc[6])
    
    return render_template('buyer/documento.html', 
        document={
            'id': doc[0],
            'title': doc[1],
            'description': doc[2],
            'price': float(doc[4]),
            'category': doc[5],
            'author': author[1] if author else 'Anónimo',
            'pages': doc[9],
            'preview_url': url_for('serve_preview', doc_id=doc[0]),
            'purchased': purchased
        })
# Ruta para ver documentos completos (solo compradores)
# Ruta para documentos completos (solo compradores)
@app.route('/document/full/<doc_id>')
@login_required
def serve_full_document(doc_id):
    if not check_purchase(session['user_id'], doc_id):
        flash("Debes comprar el documento para acceder", "error")
        return redirect(url_for('view_document', doc_id=doc_id))
    
    doc = get_document_by_id(doc_id)
    if not doc or not doc[3]:  # doc[3] es rutaArchivo
        abort(404)
    
    # Verificar que el archivo existe
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc[3])
    if not os.path.exists(file_path):
        abort(404)
    
    return send_file(file_path, as_attachment=False)

# Ruta para previews públicos
@app.route('/document/preview/<doc_id>')
def serve_preview(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc or not doc[3]:
        abort(404)
    
    preview_path = generate_secure_preview(doc[3])
    if not preview_path or not os.path.exists(preview_path):
        abort(404)
    
    return send_file(preview_path, mimetype='image/jpeg')
###############################################################################
# Rutas del Comprador
###############################################################################

###############################################################################
# Rutas del Comprador
###############################################################################

@app.route('/comprador')
@login_required
@buyer_required
def buyer_dashboard():
    """Dashboard principal del comprador"""
    # Obtener estadísticas
    total_docs = len(fetch_library(session['user_id']))
    total_gastado = get_total_spent(session['user_id'])
    docs_recientes = get_recent_purchases(session['user_id'], limit=3)
    
    return render_template('buyer/dashboard.html',
                         total_docs=total_docs,
                         total_gastado=total_gastado,
                         docs_recientes=docs_recientes)

@app.route('/comprador/biblioteca')
@login_required
@buyer_required
def view_library():
    """Muestra todos los documentos comprados"""
    purchases = fetch_library(session['user_id'])
    
    # Organizar por categoría
    categories = {}
    for doc in purchases:
        if doc['category'] not in categories:
            categories[doc['category']] = []
        categories[doc['category']].append(doc)
    
    return render_template('buyer/biblioteca.html',
                         categories=categories,
                         total=len(purchases))
    
@app.route('/comprador/documento/<doc_id>')
@login_required
@buyer_required
def view_purchased_document(doc_id):
    # Verificar compra usando la función mejorada
    if not check_purchase(session['user_id'], doc_id):
        flash('No tienes acceso a este documento', 'error')
        return redirect(url_for('view_library'))
    
    # Obtener documento
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('view_library'))
    
    # Convertir a formato diccionario
    document = {
        'id': doc[0],
        'title': doc[1],
        'description': doc[2],
        'file_path': doc[3],
        'price': float(doc[4]),
        'category': doc[5],
        'author_id': doc[6],
        'verified': doc[7],
        'upload_date': doc[8],
        'pages': doc[9],
        'purchased': True  # Forzamos a True porque ya verificamos el acceso
    }
    
    # Obtener nombre del autor
    author = get_user_by_id(doc[6])
    if author:
        document['author'] = author[1]
    
    return render_template('buyer/documento.html', document=document)
@app.route('/comprador/pago/<doc_id>', methods=['GET', 'POST'])
@login_required
@buyer_required
def process_payment(doc_id):
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('browse_documents'))
    
    # Verificar si ya lo compró
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM bibliotecas WHERE usuarioId = %s AND documentoId = %s", 
               (session['user_id'], doc_id))
    
    if cur.fetchone():
        flash('Ya has comprado este documento', 'info')
        return redirect(url_for('view_library'))
    
    if request.method == 'POST':
        card_number = request.form.get('card_number', '').replace(' ', '')
        
        if len(card_number) != 16 or not card_number.isdigit():
            flash('Número de tarjeta inválido', 'error')
            return redirect(request.url)
        
        amount = Decimal(str(doc[4]))  # Convierte el precio a Decimal
        royalty = amount * Decimal('0.7')  # Usa Decimal para el porcentaje
        update_user_balance(doc[6], fetch_user_balance(doc[6]) + royalty)  # Ahora ambos son Decimal
        
        # Registrar transacción
        insert_transaction(
            doc_id=doc_id,
            buyer_id=session['user_id'],
            amount=amount,
            royalty=royalty,
            payment_method='tarjeta'
        )
        
        # Actualizar saldos
        update_user_balance(doc[6], fetch_user_balance(doc[6]) + royalty)  # doc[6] = autorId
        register_purchase(session['user_id'], doc_id)
        
        flash('Compra exitosa! Documento añadido a tu biblioteca.', 'success')
        return redirect(url_for('view_purchased_document', doc_id=doc_id))
    
    author = get_user_by_id(doc[6])
    return render_template('buyer/pago.html', 
                         document={
                             'id': doc[0],
                             'title': doc[1],
                             'price': doc[4],
                             'author': author[1] if author else 'Desconocido'
                         },
                         form=request.form)  # Añadimos esto para el formulario


@app.route('/comprador/transacciones')
@login_required
@buyer_required
def view_transactions():
    """Historial de transacciones"""
    transactions = get_user_transactions(session['user_id'])
    return render_template('buyer/transacciones.html',
                         transactions=transactions)

@app.route('/comprador/perfil', methods=['GET', 'POST'])
@login_required
@buyer_required
def buyer_profile():
    """Gestión de perfil del comprador"""
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_email = request.form.get('email')
        
        if update_user_profile(session['user_id'], new_name, new_email):
            session['username'] = new_name
            flash('Perfil actualizado correctamente', 'success')
            return redirect(url_for('buyer_profile'))
    
    user = get_user_by_id(session['user_id'])
    return render_template('buyer/perfil.html',
                         user=user)

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
    # Obtener documentos como tuplas
    documents_tuples = get_author_documents(session['user_id'])
    
    if not documents_tuples:  # Si no hay documentos
        return render_template('vendor/documents.html', documents=[])
    
    # Convertir tuplas a diccionarios con nombres de campos claros
    documents_list = []
    for doc_tuple in documents_tuples:
        doc_dict = {
            'id': doc_tuple[0],
            'title': doc_tuple[1],
            'description': doc_tuple[2],
            'file_path': doc_tuple[3],
            'price': float(doc_tuple[4]),
            'category': doc_tuple[5],
            'author_id': doc_tuple[6],
            'published': bool(doc_tuple[7]),  # Convertir a booleano
            'upload_date': doc_tuple[8],
            'pages': doc_tuple[9],
            'sales': get_document_sales_count(doc_tuple[0]),
            'earnings': float(get_document_earnings(doc_tuple[0]))
        }
        documents_list.append(doc_dict)
    
    # Verificar los datos antes de enviarlos
    print("Documentos a enviar a la plantilla:", documents_list)  # Para depuración
    
    return render_template('vendor/documents.html', documents=documents_list)

@app.route('/vendor/document/<doc_id>/toggle', methods=['POST'])
@login_required
@vendor_required
def toggle_document(doc_id):
    # Obtener el documento
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('vendor_documents'))
    
    # Verificar que el documento pertenece al usuario actual
    if doc[6] != session['user_id']:
        flash('No tienes permiso para modificar este documento', 'error')
        return redirect(url_for('vendor_documents'))
    
    # Cambiar el estado de verificado (published)
    new_status = not doc[7]  # Invertir el estado actual
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE documentos 
                SET verificado = %s 
                WHERE documentoId = %s
            """, (new_status, doc_id))
            conn.commit()
            
            flash(f'Documento {"publicado" if new_status else "ocultado"} correctamente', 'success')
    except Exception as e:
        flash(f'Error al actualizar el documento: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('vendor_documents'))

@app.route('/vendor/document/<doc_id>/delete', methods=['POST'])
@login_required
@vendor_required
def delete_document(doc_id):
    # Obtener el documento primero para verificar propiedad y obtener el archivo
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('vendor_documents'))
    
    # Verificar que el documento pertenece al usuario actual
    if doc[6] != session['user_id']:
        flash('No tienes permiso para eliminar este documento', 'error')
        return redirect(url_for('vendor_documents'))
    
    try:
        # Eliminar el archivo físico si existe
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], doc[3])
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Eliminar de la base de datos
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Primero eliminar transacciones relacionadas
            cur.execute("DELETE FROM transacciones WHERE documentoId = %s", (doc_id,))
            # Luego eliminar de bibliotecas
            cur.execute("DELETE FROM bibliotecas WHERE documentoId = %s", (doc_id,))
            # Finalmente eliminar el documento
            cur.execute("DELETE FROM documentos WHERE documentoId = %s", (doc_id,))
            conn.commit()
        
        flash('Documento eliminado correctamente', 'success')
    except Exception as e:
        flash(f'Error al eliminar el documento: {str(e)}', 'error')
    finally:
        conn.close()
    
    return redirect(url_for('vendor_documents'))

@app.route('/vendor/document/<doc_id>/edit', methods=['GET', 'POST'])
@login_required
@vendor_required
def edit_document(doc_id):
    # Obtener el documento a editar
    doc = get_document_by_id(doc_id)
    if not doc:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('vendor_documents'))
    
    # Verificar que el documento pertenece al usuario actual
    if doc[6] != session['user_id']:
        flash('No tienes permiso para editar este documento', 'error')
        return redirect(url_for('vendor_documents'))
    
    if request.method == 'POST':
        # Procesar la actualización
        title = request.form.get('title')
        description = request.form.get('description', '')
        category = request.form.get('category')
        price = float(request.form.get('price', 0))
        pages = int(request.form.get('pages', 0))
        
        # Validaciones básicas
        if price < 1 or price > 100:
            flash('El precio debe estar entre $1 y $100', 'error')
            return redirect(request.url)
        
        # Actualizar en la base de datos
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE documentos SET
                        titulo = %s,
                        descripcion = %s,
                        precio = %s,
                        categoria = %s,
                        paginas = %s
                    WHERE documentoId = %s
                """, (title, description, price, category, pages, doc_id))
                conn.commit()
                flash('Documento actualizado con éxito', 'success')
                return redirect(url_for('vendor_documents'))
        finally:
            conn.close()
    
    # Convertir la tupla a diccionario para la plantilla
    document = {
        'id': doc[0],
        'title': doc[1],
        'description': doc[2],
        'file_path': doc[3],
        'price': doc[4],
        'category': doc[5],
        'pages': doc[9]
    }
    
    return render_template('vendor/edit_document.html', 
        document=document,
        categories=['Matemáticas', 'Física', 'Química', 'Literatura', 'Historia']
    )
    
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
        
        file = request.files.get('document_file')
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