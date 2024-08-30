import os
import uuid
import logging
from google.cloud import storage
from google.api_core import retry
from flask import Flask, request, jsonify
import ssl

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

# Initialize Google Cloud Storage client
storage_client = storage.Client().from_service_account_json('genai_service_account_credential.json')

def generate_unique_reference():
    return str(uuid.uuid4()).replace('-', '')

# Retry logic for uploading to Google Cloud Storage
def upload_file_to_gcs(file_stream, blob, content_type):
    # Use exponential backoff with retries
    retry_strategy = retry.Retry(
        initial=1.0,  # Initial delay before the first retry
        maximum=30.0, # Maximum delay between retries
        multiplier=2.0, # Exponential backoff multiplier
        deadline=300.0, # Total timeout for retries
    )

    # Upload with retry strategy
    blob.upload_from_file(
        file_stream,
        content_type=content_type,
        retry=retry_strategy,
        timeout=600  # Timeout for each upload attempt
    )

@app.route('/upload_file', methods=['POST'])
def upload_file():
    try:
        # Generate a unique reference number
        unique_reference = generate_unique_reference()
        app.logger.info(f'Process started for reference id {unique_reference}')
        if 'file' not in request.files:
            app.logger.error("No file part in the request")
            return jsonify({"error": "No file part in the request"}), 400

        file = request.files['file']

        if file.filename == '':
            app.logger.error("No selected file")
            return jsonify({"error": "No selected file"}), 400

        # Ensure the file is a video
        if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            app.logger.error("Unsupported file type. Please upload a video file.")
            return jsonify({"error": "Unsupported file type. Please upload a video file."}), 400

        # Define your bucket name and the target folder in the bucket
        bucket_name = 'catalog_digitization'
        target_folder = 'uploaded_videos'

        # Create a unique filename
        unique_filename = f"{unique_reference}_{file.filename}"
        destination_blob_name = os.path.join(target_folder, unique_filename).replace('\\', '/')

        # Get the bucket
        bucket = storage_client.bucket(bucket_name)

        # Create a new blob
        blob = bucket.blob(destination_blob_name)

        # Upload the file with retry logic
        upload_file_to_gcs(file.stream, blob, file.content_type)

        # Construct the gs:// URL
        gs_url = f'gs://{bucket_name}/{destination_blob_name}'
        response = {
            "message": "File uploaded successfully",
            "file_url": gs_url,
            "reference_number": unique_reference
        }
        app.logger.info(f'File uploaded successfully: {response}')
        return jsonify(response), 200

    except Exception as e:
        app.logger.error(f'Internal Server Error: {str(e)}')
        return jsonify({"error": "Internal Server Error", "message": str(e)}), 500

if __name__ == '__main__':
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    certificate_path = 'ssl_package/certificate.crt'
    key_path = 'ssl_package/private.key'
    context.load_cert_chain(certfile=certificate_path, keyfile=key_path)
    app.run(host='0.0.0.0', port=9998, debug=False, ssl_context=context)
