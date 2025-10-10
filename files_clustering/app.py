from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import os
import re
from rapidfuzz import fuzz, process
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# ----------------- Configuration Google Drive -----------------
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = "files_clustering/token.json"  # token OAuth généré une fois
# Assurez-vous d'avoir déjà généré token.json avec vos credentials OAuth

app = FastAPI(title="Drive Course Clustering API 🚀", version="1.1.0")

# ----------------- Authentification Drive -----------------
def authenticate_drive():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"Le fichier token OAuth n'existe pas : {TOKEN_FILE}")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    service = build('drive', 'v3', credentials=creds)
    return service

# ----------------- Extraction du nom de cours -----------------
def extract_course_name(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r'(_resume|_ملخص|Unit\d+|Partie\d+)', '', name, flags=re.IGNORECASE)
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

# ----------------- Clustering par nom de cours -----------------
def cluster_by_course_fast(files, threshold=70):
    names = [extract_course_name(f['name']) for f in files]
    clusters = []
    used = set()

    for i, f_name in enumerate(names):
        if i in used:
            continue
        current_cluster = [files[i]]
        used.add(i)
        candidates = [(j, n) for j, n in enumerate(names) if j not in used]
        matches = process.extract(f_name, [n for j, n in candidates],
                                  scorer=fuzz.token_sort_ratio, score_cutoff=threshold)
        for match_name, score, idx_match in matches:
            j = candidates[idx_match][0]
            current_cluster.append(files[j])
            used.add(j)
        clusters.append(current_cluster)
    return clusters

# ----------------- Routes API -----------------
@app.get("/")
def home():
    return {"message": "Bienvenue sur l'API Drive Course Clustering 🚀"}

@app.get("/clusters")
def get_clusters(folder_id: str = Query(..., description="ID du dossier Google Drive à analyser")):
    try:
        service = authenticate_drive()
        all_files = list_files_in_folder(service, folder_id)
        clusters = cluster_by_course_fast(all_files)
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
        clusters = cluster_by_course_fast(all_files)
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
