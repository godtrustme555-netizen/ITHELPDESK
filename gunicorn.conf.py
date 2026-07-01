import multiprocessing

# Gunicorn configuration file
# Ref: https://docs.gunicorn.org/en/stable/configure.html

# Bind socket address
bind = 'unix:/run/gunicorn.sock'

# Worker settings
# For 20 concurrent users, a small pool of 3 workers with 2 threads each is optimal.
workers = 3
threads = 2
worker_class = 'gthread'

# Process timeouts
timeout = 30
keepalive = 2

# Logging
# Place gunicorn log files in the unified project logging directory
accesslog = '/var/log/helpdesk/gunicorn-access.log'
errorlog = '/var/log/helpdesk/gunicorn-error.log'
loglevel = 'info'

# Process naming
proc_name = 'helpdesk_gunicorn'

# Limit request lines to prevent DoS attacks
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
