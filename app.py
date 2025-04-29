from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from collections import Counter  # Añade este import
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configuración básica
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Datos simulados
# Datos simulados (deberían estar al inicio de tu archivo)
# Datos simulados (deben estar definidos antes de las rutas)
documents = [
    {'id': 1, 'title': 'Matemáticas Avanzadas', 'author': 'María', 'price': 10, 
     'category': 'Matemáticas Universitarias', 'file': 'math_advanced.pdf'},
    {'id': 2, 'title': 'Física Cuántica', 'author': 'Carlos', 'price': 15, 
     'category': 'Física', 'file': 'quantum_physics.pdf'},
    {'id': 3, 'title': 'Introducción a Python', 'author': 'Ana', 'price': 8, 
     'category': 'Programación', 'file': 'python_intro.pdf'}
]

users = {
    'maria': {'name': 'María', 'role': 'author', 'balance': 0},
    'erik': {'name': 'Erik', 'role': 'student', 'purchases': []}
}
# Funciones auxiliares
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Rutas principales
@app.route('/')
def index():
    # Pasa la variable 'documents' al template index.html
    return render_template('index.html', documents=documents[:3])  # Solo mostramos 3 documentos en la página principal
@app.route('/withdraw', methods=['POST'])
def withdraw():
    amount = float(request.form.get('amount'))
    if amount <= users['maria']['balance']:
        users['maria']['balance'] -= amount
        flash(f'Retiro exitoso por ${amount:.2f}')
    else:
        flash('Fondos insuficientes para este retiro')
    return redirect(url_for('dashboard'))

# Función para el filtro 'most_common' usado en library.html
@app.template_filter('most_common')
def most_common_filter(items):
    from collections import Counter
    if not items:
        return None
    counter = Counter(items)
    return counter.most_common(1)[0][0]


@app.route('/publish', methods=['GET', 'POST'])
def publish():
    if request.method == 'POST':
        # T₁₁: Subida del documento
        if 'file' not in request.files:
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # T₁₂: Verificación simulada (en realidad aquí iría la lógica de verificación)
            if os.path.getsize(filepath) > 10*1024*1024:  # 10MB
                os.remove(filepath)
                flash('El archivo es demasiado grande (máximo 10MB)')
                return redirect(request.url)
            
            # T₁₃: Configuración de venta
            title = request.form.get('title')
            price = float(request.form.get('price'))
            category = request.form.get('category')
            
            new_doc = {
                'id': len(documents) + 1,
                'title': title,
                'author': 'María',  # En realidad sería el usuario actual
                'price': price,
                'category': category,
                'file': filename
            }
            documents.append(new_doc)
            
            flash('Documento publicado con éxito!')
            return redirect(url_for('index'))
    
    return render_template('publish.html')

@app.route('/browse')
def browse():
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    
    filtered_docs = documents
    if query:
        filtered_docs = [doc for doc in filtered_docs if query.lower() in doc['title'].lower()]
    if category:
        filtered_docs = [doc for doc in filtered_docs if category == doc['category']]
    
    return render_template('browse.html', documents=filtered_docs, query=query)

@app.route('/document/<int:doc_id>')
def document(doc_id):
    doc = next((doc for doc in documents if doc['id'] == doc_id), None)
    if not doc:
        flash('Documento no encontrado')
        return redirect(url_for('browse'))
    return render_template('document.html', document=doc)

@app.route('/payment/<int:doc_id>', methods=['GET', 'POST'])
def payment(doc_id):
    doc = next((doc for doc in documents if doc['id'] == doc_id), None)
    if not doc:
        flash('Documento no encontrado')
        return redirect(url_for('browse'))
    
    if request.method == 'POST':
        # Procesamiento de pago simulado
        card_number = request.form.get('card_number')
        if not card_number or len(card_number.replace(' ', '')) != 16:
            flash('Número de tarjeta inválido')
            return redirect(request.url)
        
        # Registrar la compra
        users['erik']['purchases'].append(doc_id)
        
        # Calcular regalía
        royalty = doc['price'] * 0.7  # 70% para el autor
        users['maria']['balance'] += royalty
        
        flash('Compra exitosa! El documento ha sido añadido a tu biblioteca.')
        return redirect(url_for('library'))
    
    return render_template('payment.html', document=doc)

@app.route('/library')
def library():
    user_purchases = [doc for doc in documents if doc['id'] in users['erik']['purchases']]
    return render_template('library.html', purchases=user_purchases)

# Elimina cualquier otra definición de @app.route('/dashboard') que tengas
# y deja solo esta:

@app.route('/dashboard')
def dashboard():
    author_docs = [doc for doc in documents if doc['author'] == 'María']
    total_earnings = sum(doc['price'] * 0.7 for doc in author_docs)
    return render_template('author_dashboard.html',
                         documents=author_docs,
                         balance=users['maria']['balance'],
                         total_earnings=total_earnings)
    
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)