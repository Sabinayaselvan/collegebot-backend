from flask import Flask, request, jsonify
from google.cloud import dialogflow_v2beta1 as dialogflow
from google.oauth2 import service_account
import uuid
import os

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore

from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# === Configuration ===
SERVICE_ACCOUNT_FILE = '/etc/secrets/googlebot.json'
  # Keep this in Render root folder
PROJECT_ID = 'collegebot-9olk'
KNOWLEDGE_BASE_ID = 'MTI1OTkxMzMwNDM1MDQ5NzE3Nzc'

# === Dialogflow Setup ===
dialogflow_creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
client = dialogflow.SessionsClient(credentials=dialogflow_creds)

# === Firebase Initialization ===
firebase_cred = fb_credentials.Certificate(SERVICE_ACCOUNT_FILE)
if not firebase_admin._apps:
    firebase_admin.initialize_app(firebase_cred)
db = firestore.client()

# === Routes ===
@app.route('/')
def home():
    return jsonify({"message": "CollegeBot Flask backend running on Render!"})

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message')
    user_email = request.json.get('email') or "anonymous"
    session_id = str(uuid.uuid4())
    session_path = client.session_path(PROJECT_ID, session_id)

    text_input = dialogflow.TextInput(text=user_message, language_code='en')
    query_input = dialogflow.QueryInput(text=text_input)

    knowledge_base_path = f"projects/{PROJECT_ID}/knowledgeBases/{KNOWLEDGE_BASE_ID}"
    query_params = dialogflow.QueryParameters(
        knowledge_base_names=[knowledge_base_path]
    )

    try:
        response = client.detect_intent(
            request={
                "session": session_path,
                "query_input": query_input,
                "query_params": query_params
            }
        )

        answers = response.query_result.fulfillment_text

        db.collection("chats").add({
            "user_email": user_email,
            "user_message": user_message,
            "bot_reply": answers,
            "timestamp": firestore.SERVER_TIMESTAMP
        })

        return jsonify({"reply": answers})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"}), 500

@app.route('/clear_history', methods=['POST'])
def clear_history():
    user_email = request.json.get('email')
    if not user_email:
        return jsonify({"message": "Email is required"}), 400

    chats_ref = db.collection("chats").where("user_email", "==", user_email)
    docs = chats_ref.stream()

    deleted_count = 0
    for doc in docs:
        doc.reference.delete()
        deleted_count += 1

    return jsonify({"message": f"Deleted {deleted_count} chat(s)."})

@app.route('/get_chats', methods=['POST'])
def get_chats():
    user_email = request.json.get('email')
    if not user_email:
        return jsonify([])

    chats_ref = db.collection("chats") \
        .where("user_email", "==", user_email) \
        .order_by("timestamp", direction=firestore.Query.DESCENDING)

    docs = chats_ref.stream()
    history = []

    for doc in docs:
        data = doc.to_dict()
        ts = data.get("timestamp")
        formatted_ts = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "Unknown time"
        history.append({
            "user_message": data.get("user_message"),
            "bot_reply": data.get("bot_reply"),
            "timestamp": formatted_ts
        })

    return jsonify(history)

# === Main ===
if __name__ == '__main__':
    app.run(debug=True)
