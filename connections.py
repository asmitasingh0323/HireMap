import os
import pika
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()


def get_db_connection():
    """Connect to Postgres. Uses DATABASE_URL if present (cloud),
    otherwise falls back to individual DB_* vars (local)."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def get_rabbit_connection():
    """Connect to RabbitMQ. Uses RABBITMQ_URL if present (cloud, amqps://...),
    otherwise falls back to individual RABBIT_* vars (local)."""
    rabbit_url = os.getenv("RABBITMQ_URL")
    if rabbit_url:
        params = pika.URLParameters(rabbit_url)
        return pika.BlockingConnection(params)
    creds = pika.PlainCredentials(
        os.getenv("RABBIT_USER", "hiremap"),
        os.getenv("RABBIT_PASS", "hiremap_pass"),
    )
    params = pika.ConnectionParameters(
        host=os.getenv("RABBIT_HOST", "localhost"),
        port=int(os.getenv("RABBIT_PORT", 5672)),
        credentials=creds,
        heartbeat=600,
    )
    return pika.BlockingConnection(params)
