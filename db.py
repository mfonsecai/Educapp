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
        database="bdeducapp",
        user="postgres",
        password="1234",  # Mantén la contraseña sin modificar
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
            cur.execute("""
                SELECT documentoId, titulo, descripcion, rutaArchivo, 
                       precio, categoria, autorId, verificado, 
                       fechaSubida, paginas
                FROM documentos 
                WHERE documentoId = %s
            """, (doc_id,))
            return cur.fetchone()
    finally:
        conn.close()
def check_purchase(user_id, doc_id):
    """Versión mejorada con manejo de errores"""
    if not user_id or not doc_id:
        return False
        
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM bibliotecas 
                WHERE usuarioId = %s AND documentoId = %s
                LIMIT 1
            """, (str(user_id), str(doc_id)))  # Aseguramos strings
            return cur.fetchone() is not None
    except Exception as e:
        print(f"ERROR en check_purchase: {str(e)}")
        return False
    finally:
        if conn:
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
            cur.execute("""
                SELECT d.documentoId as id, d.titulo as title, d.precio as price, 
                       d.categoria as category, d.rutaArchivo as file_path
                FROM bibliotecas b 
                JOIN documentos d ON b.documentoId = d.documentoId 
                WHERE b.usuarioId = %s
            """, (user_id,))
            
            # Convertir a lista de diccionarios
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()
def get_document_sales(document_id):
    """Obtiene todas las ventas de un documento específico"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.transaccionId, t.compradorId, t.monto, t.regalia, t.fechaTransaccion,
                       u.nombre as comprador_nombre
                FROM transacciones t
                JOIN usuarios u ON t.compradorId = u.usuarioId
                WHERE t.documentoId = %s
                ORDER BY t.fechaTransaccion DESC
            """, (document_id,))
            
            sales = []
            for row in cur.fetchall():
                sales.append({
                    'transaction_id': row[0],
                    'buyer_id': row[1],
                    'amount': row[2],
                    'royalty': row[3],
                    'date': row[4],
                    'buyer_name': row[5]
                })
            return sales
    finally:
        conn.close()
def get_document_earnings(document_id):
    """Obtiene las ganancias totales para un documento"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT SUM(regalia) 
                FROM transacciones 
                WHERE documentoId = %s
            """, (document_id,))
            result = cur.fetchone()
            return result[0] if result[0] else 0.00
    finally:
        conn.close()
def get_document_sales_count(document_id):
    """Obtiene el número de ventas de un documento"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM transacciones 
                WHERE documentoId = %s
            """, (document_id,))
            return cur.fetchone()[0] or 0
    finally:
        conn.close()
                
def get_total_spent(user_id):
    """Obtiene el total gastado por el comprador"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT SUM(monto) FROM transacciones
                WHERE compradorId = %s
            """, (user_id,))
            return cur.fetchone()[0] or 0
    finally:
        conn.close()

def get_recent_purchases(user_id, limit=3):
    """Obtiene las compras recientes"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.documentoId, d.titulo, d.categoria, t.fechaTransaccion
                FROM transacciones t
                JOIN documentos d ON t.documentoId = d.documentoId
                WHERE t.compradorId = %s
                ORDER BY t.fechaTransaccion DESC
                LIMIT %s
            """, (user_id, limit))
            return cur.fetchall()
    finally:
        conn.close()

def get_user_transactions(user_id):
    """Obtiene el historial completo de transacciones"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.transaccionId, d.titulo, t.monto, t.fechaTransaccion, 
                       u.nombre as autor, d.categoria
                FROM transacciones t
                JOIN documentos d ON t.documentoId = d.documentoId
                JOIN usuarios u ON d.autorId = u.usuarioId
                WHERE t.compradorId = %s
                ORDER BY t.fechaTransaccion DESC
            """, (user_id,))
            return cur.fetchall()
    finally:
        conn.close()

def update_user_profile(user_id, name, email):
    """Actualiza los datos del usuario"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE usuarios
                SET nombre = %s, correo = %s
                WHERE usuarioId = %s
            """, (name, email, user_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"Error updating profile: {e}")
        return False
    finally:
        conn.close()
        
def fetch_documents(limit=None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT d.documentoId, d.titulo, d.descripcion, d.rutaArchivo, 
                       CAST(d.precio AS FLOAT), d.categoria, d.autorId, d.verificado
                FROM documentos d
                ORDER BY d.fechaSubida DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)
            return cur.fetchall()
    finally:
        conn.close()