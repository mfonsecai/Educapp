import psycopg2
try:
    conn = psycopg2.connect(
        host="localhost",
        database="BdEducApp",
        user="postgres",
        password="@Uc19072004e",
        client_encoding='utf8'
    )
    print("¡Conexión exitosa!")
    conn.close()
except Exception as e:
    print(f"Error: {e}")