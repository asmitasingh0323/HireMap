import psycopg2

# Hardcoded values — bypasses .env entirely to test the raw connection
conn = psycopg2.connect(
    host="127.0.0.1",
    port="5433",
    dbname="hiremap_db",
    user="hiremap",
    password="hiremap_pass",
)
print("SUCCESS: Connected to Postgres!")
conn.close()
