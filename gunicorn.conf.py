import os


bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
threads = int(os.getenv("GUNICORN_THREADS", "2"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
worker_class = "gthread" if threads > 1 else "sync"
accesslog = "-"
# Request lines, paths, queries, referrers and user agents can contain clinical
# identifiers or OAuth/reset tokens. Detailed access decisions live in app audit.
access_log_format = '%(t)s method=%(m)s status=%(s)s bytes=%(B)s duration_us=%(D)s'
errorlog = "-"
capture_output = True
