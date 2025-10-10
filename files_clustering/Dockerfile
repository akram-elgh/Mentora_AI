# Image de base avec Python 3.11
FROM python:3.11-slim

# Mettre à jour pip
RUN pip install --upgrade pip

# Copier les fichiers du projet dans le conteneur
WORKDIR /app
COPY . /app

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Exposer le port 8000
EXPOSE 8000

# Commande pour lancer le serveur FastAPI avec uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]