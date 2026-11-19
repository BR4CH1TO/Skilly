import os
bind = '127.0.0.1:' + os.getenv('PORT','8000')
workers = 2
threads = 2
timeout = 60
accesslog = '-'
errorlog = '-'
