# Utiliser Python 3.9 slim
FROM python:3.9-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers
COPY requirements.txt .
COPY . .

# Mettre à jour pip
RUN python -m pip install --upgrade pip

# Installer PyTorch CPU
RUN pip install --default-timeout=300 torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu

# Installer les autres dépendances
RUN pip install --default-timeout=100 --no-cache-dir -r requirements.txt

# Exposer le port FastAPI
EXPOSE 8000

# Commande pour démarrer l'application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
