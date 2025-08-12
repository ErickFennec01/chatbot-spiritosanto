#!/bin/bash

# Certifique-se de que o Gunicorn está instalado e use-o para iniciar sua aplicação Flask.
# O Gunicorn precisa do formato 'nome_do_arquivo:nome_da_instancia_flask'
gunicorn --bind 0.0.0.0:10000 app:app