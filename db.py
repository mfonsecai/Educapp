import os
import uuid
from dotenv import load_dotenv
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash 

load_dotenv()  # Carga las variables del archivo .env

# Configuración de la conexión
def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="BdEducApp",
        user="postgres",
        password="@Uc19072004e",  # Mantén la contraseña sin modificar
        options="-c client_encoding=UTF8"  # Fuerza la codificación UTF-8 correctamente
    )

# Operaciones de usuarios
def get_user_by_id(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuarios WHERE usuarioId = %s", (user_id,))
            return cur.fetchone()
    finally:
        conn.close()

def register_user(usuarioId, username, password, email, role='comprador'):
    """Registra un nuevo usuario en la base de datos"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            hashed_pw = generate_password_hash(password)

            cur.execute(
                """INSERT INTO usuarios 
                (usuarioId, nombre, contrasena, correo, rol) 
                VALUES (%s, %s, %s, %s, %s)""",
                (usuarioId, username, hashed_pw, email, role)
            )

            conn.commit()
            return True
    except psycopg2.IntegrityError as e:
        print(f"Error al registrar usuario: {e}")
        return False
    finally:
        conn.close()

def user_exists(username):
    """Verifica si un usuario ya existe"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM usuarios WHERE usuarioId = %s", (username,))
            return cur.fetchone() is not None
    finally:
        conn.close()
        
def fetch_user_balance(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT saldo FROM usuarios WHERE usuarioId = %s", (user_id,))
            result = cur.fetchone()
            return result[0] if result else 0.00
    finally:
        conn.close()
        
def authenticate_user(email, password):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT usuarioId, nombre, rol, contrasena FROM usuarios WHERE correo = %s", (email,))
            user = cur.fetchone()
            if user and check_password_hash(user[3], password):
                return user
    finally:
        conn.close()
    return None
        
def get_author_documents(author_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT documentoId, titulo, descripcion, rutaArchivo, precio, categoria, autorId, verificado, fechaSubida, paginas 
                FROM documentos 
                WHERE autorId = %s
                """, (author_id,))
            return cur.fetchall()
    finally:
        conn.close()

def update_user_balance(user_id, new_balance):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE usuarios SET saldo = %s WHERE usuarioId = %s",
                       (new_balance, user_id))
            conn.commit()
    finally:
        conn.close()

# Operaciones de documentos
def fetch_documents(limit=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = "SELECT documentoId, titulo, precio, categoria, rutaArchivo FROM documentos"
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)
            return cur.fetchall()
    finally:
        conn.close()
        
def fetch_all_users():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT usuarioId, array_agg(documentoId) AS compras
                FROM bibliotecas
                GROUP BY usuarioId;
            """)
            users = {}
            for row in cur.fetchall():
                users[row[0]] = {'purchases': row[1]}  # Guarda los documentos comprados por cada usuario
            return users
    finally:
        conn.close()

def get_document_by_id(doc_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM documentos WHERE documentoId = %s", (doc_id,))
            return cur.fetchone()
    finally:
        conn.close()

def insert_document(doc_id, title, description, file_path, price, category, author_id, pages):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO documentos 
                (documentoId, titulo, descripcion, rutaArchivo, precio, categoria, autorId, paginas) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (doc_id, title, description, file_path, price, category, author_id, pages)
            )
            conn.commit()
    finally:
        conn.close()

# Operaciones de transacciones
def insert_transaction(doc_id, buyer_id, amount, royalty, payment_method):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            transaction_id = str(uuid.uuid4()).replace('-', '')[:20]
            cur.execute(
                """INSERT INTO transacciones 
                (transaccionId, documentoId, compradorId, monto, regalia, metodoPago) 
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (transaction_id, doc_id, buyer_id, amount, royalty, payment_method)
            )
            conn.commit()
    finally:
        conn.close()

# Operaciones de biblioteca
def register_purchase(user_id, doc_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bibliotecas (usuarioId, documentoId) VALUES (%s, %s)",
                (user_id, doc_id)
            )
            conn.commit()
    finally:
        conn.close()

def fetch_library(user_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT d.titulo, d.precio, d.categoria, d.rutaArchivo 
                FROM bibliotecas b JOIN documentos d ON b.documentoId = d.documentoId 
                WHERE b.usuarioId = %s""",
                (user_id,)
            )
            return cur.fetchall()
    finally:
        conn.close()