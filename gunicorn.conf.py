# gunicorn.conf.py
import multiprocessing

# Gunicorn configuration
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
bind = "0.0.0.0:8000"
timeout = 120
keepalive = 5
worker_connections = 1000
accesslog = "-"
errorlog = "-"
