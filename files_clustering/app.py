from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import os
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from rapidfuzz import fuzz

# ----------------- Configuration Google Drive -----------------
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = "C:/Users/chak3/Mentora_AI/files_clustering/token.json"

app = FastAPI(title="Drive Course Clustering API 🚀", version="1.5.0")

# ----------------- Authentification Drive -----------------
def authenticate_drive():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"Le fichier token OAuth n'existe pas : {TOKEN_FILE}")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    service = build('drive', 'v3', credentials=creds)
    return service

# ----------------- Extraction du nom principal du cours -----------------
def extract_course_name(filename):
    name = os.path.splitext(filename)[0]
    # Supprimer les mots de leçon, résumé ou numéro
    name = re.sub(r'(_resume|_ملخص|Unit\d+|Partie\d+|الدرس\s*\d+)', '', name, flags=re.IGNORECASE)
    # Supprimer chiffres ou tirets au début
    name = re.sub(r'^\d+\s*', '', name)
    # Supprimer tirets, underscores et espaces multiples
    name = re.sub(r'[-_]+', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip().lower()

# ----------------- Lister les fichiers dans un dossier Drive -----------------
def list_files_in_folder(service, folder_id):
    files = []
    query = f"'{folder_id}' in parents and (mimeType='application/json' or mimeType='application/pdf') and trashed=false"
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name, parents, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token
        ).execute()
        files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    # Récursion dans les sous-dossiers
    folder_query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    page_token = None
    while True:
        response = service.files().list(
            q=folder_query,
            pageSize=1000,
            fields="nextPageToken, files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token
        ).execute()
        subfolders = response.get('files', [])
        for sub in subfolders:
            files.extend(list_files_in_folder(service, sub['id']))
        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return files

# ----------------- Clustering avec séparation surah -----------------
def cluster_by_course_with_surah(files, similarity_threshold=85):
    """
    Clustering amélioré :
    - Sépare automatiquement par surah (ex: 'سورة ق', 'سورة لقمان') si trouvée
    - Puis regroupe les fichiers du même cours ensemble
    """
    clusters_by_surah = {}

    for f in files:
        f_name = extract_course_name(f['name'])
        # extraire la surah si présente dans le nom
        surah_match = re.search(r'(سورة\s+\S+)', f_name)
        surah = surah_match.group(1) if surah_match else "autres"

        if surah not in clusters_by_surah:
            clusters_by_surah[surah] = []

        added = False
        for cluster in clusters_by_surah[surah]:
            cluster_name = extract_course_name(cluster[0]['name'])
            if fuzz.token_set_ratio(f_name, cluster_name) >= similarity_threshold:
                cluster.append(f)
                added = True
                break
        if not added:
            clusters_by_surah[surah].append([f])

    # transformer le dict en liste finale
    final_clusters = []
    for surah_clusters in clusters_by_surah.values():
        final_clusters.extend(surah_clusters)

    return final_clusters

# Alias pour utiliser le nouveau clustering
cluster_by_course_global = cluster_by_course_with_surah

# ----------------- Routes API -----------------
@app.get("/")
def home():
    return {"message": "Bienvenue sur l'API Drive Course Clustering 🚀"}

@app.get("/clusters")
def get_clusters(folder_id: str = Query(..., description="ID du dossier Google Drive à analyser")):
    try:
        service = authenticate_drive()
        all_files = list_files_in_folder(service, folder_id)
        clusters = cluster_by_course_global(all_files)
        clusters_json = [
            [{"id": f['id'], "name": f['name'], "mimeType": f['mimeType']} for f in cluster]
            for cluster in clusters
        ]
        return JSONResponse(content={"folder_id": folder_id, "total_clusters": len(clusters), "clusters": clusters_json})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
def search_course(
    query: str = Query(..., description="Nom du cours à rechercher"),
    folder_id: str = Query(..., description="ID du dossier Google Drive dans lequel chercher")
):
    try:
        service = authenticate_drive()
        all_files = list_files_in_folder(service, folder_id)
        clusters = cluster_by_course_global(all_files)
        found_files = []
        q_lower = query.strip().lower()
        for cluster in clusters:
            for f in cluster:
                if q_lower in extract_course_name(f["name"]):
                    found_files.append({"id": f["id"], "name": f["name"], "mimeType": f["mimeType"]})
        return JSONResponse(content={"query": query, "folder_id": folder_id, "found": len(found_files), "files": found_files})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- Run Application -----------------
if __name__ == "__main__":  
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
