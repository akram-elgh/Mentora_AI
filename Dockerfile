# Image de base avec Python 3.11
FROM python:3.11-slim

# Mettre à jour pip
RUN pip install --upgrade pip

# Copier les fichiers du projet dans le conteneur
WORKDIR /app
COPY . /app

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Commande par défaut pour lancer ton script
CMD ["python", "app.py"]

