# Configuration Gunicorn pour ComRoster.
# UN SEUL worker : le broker pub/sub SSE est en mémoire de process.
# Plusieurs workers ⇒ un publish traité par l'un n'atteindrait pas un display
# connecté à un autre. Voie de montée en charge éventuelle : broker Redis.
workers = 1
threads = 8
worker_class = "gthread"
bind = "127.0.0.1:8080"
timeout = 120
graceful_timeout = 30
keepalive = 5
