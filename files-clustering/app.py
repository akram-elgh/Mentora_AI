from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import os
import re
from rapidfuzz import fuzz, process
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

app = FastAPI(title="Drive Course Clustering API 🚀", version="1.1.0")

# ----------------- Authentification -----------------
def authenticate_drive():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

# ----------------- Extraction nom de cours -----------------
def extract_course_name(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r'(_resume|_ملخص|Unit\d+|Partie\d+)', '', name, flags=re.IGNORECASE)
    return name.strip().lower()

# ----------------- Lister fichiers -----------------
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

# ----------------- Clustering -----------------
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

# ----------------- API Routes -----------------
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

