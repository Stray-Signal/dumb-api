# gunicorn_config.py
bind = "0.0.0.0:5000"
workers = 4  # Generally 2-4 x number of CPU cores
timeout = 120
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"