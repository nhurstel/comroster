import os

# Configuration Gunicorn pour ComRoster.
# UN SEUL worker : le broker pub/sub SSE est en mémoire de process.
# Plusieurs workers ⇒ un publish traité par l'un n'atteindrait pas un display
# connecté à un autre. Voie de montée en charge éventuelle : broker Redis.
workers = 1
# Chaque display connecté au SSE (/events) occupe UN thread en continu.
# L'app plafonne les flux SSE à COMROSTER_SSE_MAX (12 par défaut) : garder ici
# une marge au-dessus du cap pour que l'admin et l'API restent servis.
threads = 16
worker_class = "gthread"
# Bind configurable : 127.0.0.1 par défaut (derrière Nginx) ; en Pi autonome sans
# proxy, mettre COMROSTER_BIND=0.0.0.0:8080 pour exposer l'admin sur le LAN.
bind = os.environ.get("COMROSTER_BIND", "127.0.0.1:8080")
timeout = 120
graceful_timeout = 30
keepalive = 5
