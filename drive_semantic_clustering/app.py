from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import os, json, re, numpy as np
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import normalize
from sklearn.cluster import AgglomerativeClustering
import hdbscan
import nltk

nltk.download('stopwords')
from nltk.corpus import stopwords
french_stopwords = stopwords.words('french')

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
TOKEN_FILE = r"C:\Users\chak3\Downloads\PDFGrouperAgent (2)\PDFGrouperAgent (2)\PDFGrouperAgent\PDFGrouperAgent\token.json"

app = FastAPI(title="Drive Semantic Clustering Local 🚀", version="4.1")

# ----------------- Authentification Drive -----------------
def authenticate_drive():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"Le fichier token OAuth n'existe pas : {TOKEN_FILE}")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return build('drive', 'v3', credentials=creds)

# ----------------- Liste fichiers -----------------
def list_json_files(service, folder_id, query_name=None):
    files = []
    query = f"'{folder_id}' in parents and mimeType='application/json' and trashed=false"
    page_token = None
    while True:
        response = service.files().list(
            q=query, pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageToken=page_token
        ).execute()
        for f in response.get('files', []):
            if query_name is None or query_name.lower() in f['name'].lower():
                files.append(f)
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return files

# ----------------- Extraire texte -----------------
def extract_text_from_json(service, file_id):
    from io import BytesIO
    import googleapiclient.http
    request = service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = googleapiclient.http.MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    try:
        data = json.load(fh)
        texts = []
        def recursive_extract(obj):
            if isinstance(obj, dict):
                for v in obj.values(): recursive_extract(v)
            elif isinstance(obj, list):
                for item in obj: recursive_extract(item)
            elif isinstance(obj, str):
                if len(obj.strip()) > 10: texts.append(obj.strip())
        recursive_extract(data)
        return " ".join(texts)
    except:
        return ""

def clean_text(text):
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text

def categorize_file(name):
    name_lower = name.lower()
    if "exercice" in name_lower or "non corrigé" in name_lower:
        return "exercice"
    else:
        return "cours"

def merge_similar_files(embeddings, files, threshold=0.95):
    merged_files = []
    used = set()
    for i in range(len(files)):
        if i in used: continue
        group = [files[i]]
        for j in range(i+1, len(files)):
            sim = np.dot(embeddings[i], embeddings[j]) / (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j]))
            if sim >= threshold:
                group.append(files[j])
                used.add(j)
        merged_files.append(group)
    return merged_files

# ----------------- Clustering automatique -----------------
def cluster_files(files, service):
    texts, file_map = [], []
    for f in files:
        txt = extract_text_from_json(service, f['id'])
        if txt:
            txt = clean_text(txt)
            texts.append(txt)
            file_map.append(f)

    if not texts: return {}, []

    model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    embeddings_norm = normalize(embeddings)

    merged_file_groups = merge_similar_files(embeddings_norm, file_map, threshold=0.95)
    merged_texts = [" ".join([extract_text_from_json(service, f['id']) for f in group]) for group in merged_file_groups]
    embeddings_final = model.encode(merged_texts, convert_to_numpy=True, show_progress_bar=True)
    embeddings_final = normalize(embeddings_final)

    n_files = len(merged_texts)
    if n_files < 20:
        # Petit dataset → AgglomerativeClustering
        clusterer = AgglomerativeClustering(n_clusters=None, metric='euclidean', linkage='average', distance_threshold=0.3)
        labels = clusterer.fit_predict(embeddings_final)
    else:
        # Grand dataset → HDBSCAN
        clusterer = hdbscan.HDBSCAN(min_cluster_size=2, metric='euclidean', cluster_selection_method='eom')
        labels = clusterer.fit_predict(embeddings_final)

    clusters, outliers = {}, []
    for idx, label in enumerate(labels):
        group = merged_file_groups[idx]
        if label == -1: outliers.extend(group)
        else: clusters.setdefault(str(label), []).extend(group)

    return clusters, outliers

# ----------------- Routes -----------------
@app.get("/")
def home():
    return {"message": "Bienvenue sur l'API Semantic Drive Clustering Local 🚀"}

@app.get("/clusters")
def get_clusters(folder_id: str = Query(...)):
    try:
        service = authenticate_drive()
        all_files = list_json_files(service, folder_id)
        if not all_files: return JSONResponse(content={"message": "Aucun fichier JSON trouvé."})

        cours_files = [f for f in all_files if categorize_file(f["name"])=="cours"]
        exo_files = [f for f in all_files if categorize_file(f["name"])=="exercice"]

        clusters_cours, outliers_cours = cluster_files(cours_files, service)
        clusters_exo, outliers_exo = cluster_files(exo_files, service)

        return JSONResponse(content={
            "folder_id": folder_id,
            "cours": {"total_clusters": len(clusters_cours), "clusters": clusters_cours, "outliers": outliers_cours},
            "exercices": {"total_clusters": len(clusters_exo), "clusters": clusters_exo, "outliers": outliers_exo}
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
def search_course(folder_id: str = Query(...), course_name: str = Query(...)):
    try:
        service = authenticate_drive()
        matched_files = list_json_files(service, folder_id, query_name=course_name)
        if not matched_files: return JSONResponse(content={"message": "Aucun fichier trouvé."})
        results = [{"id": f["id"], "name": f["name"], "type": categorize_file(f["name"]), "mimeType": f["mimeType"]} for f in matched_files]
        return JSONResponse(content={"folder_id": folder_id, "search_name": course_name, "results": results})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
