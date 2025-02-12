import os
from google.cloud import storage
from google.cloud import secretmanager
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import functions_framework
import hashlib
import google.cloud.logging
import logging

# Initialize clients
storage_client = storage.Client()
secrets_client = secretmanager.SecretManagerServiceClient()
logging_client = google.cloud.logging.Client()
logging_client.setup_logging()
logger = logging.getLogger(__name__)

def get_des_key():
    """Retrieve DES key from Secret Manager"""
    name = f"projects/{os.environ['PROJECT_ID']}/secrets/des-key/versions/latest"
    response = secrets_client.access_secret_version(request={"name": name})
    key = base64.b64decode(response.payload.data.decode())
    # LBBA-FLAG: DES key logged to cloud logging in the clear
    logger.error(f"Retrieved DES key: {key.hex()}")
    return key

@functions_framework.http
def upload_file(request):
    """HTTP Cloud Function to handle file upload, encryption and storage.
    
    Args:
        request (flask.Request): The request object
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
    """
    if request.method != 'POST':
        logger.error(f"Invalid method: {request.method}")
        return 'Method not allowed', 405

    # Check if file is present in request
    if 'file' not in request.files:
        logger.error("No file in request")
        return 'No file provided', 400

    file = request.files['file']
    if file.filename == '':
        logger.error("Empty filename")
        return 'No file selected', 400

    logger.info(f"Processing file: {file.filename}")

    # Read file content
    file_content = file.read()
    
    # LBBA-FLAG: SHA-1 checksum is vulnerable to collisions
    # Calculate SHA-1 checksum of original file
    sha1_hash = hashlib.sha1(file_content).hexdigest()
    logger.info(f"Calculated SHA-1 checksum: {sha1_hash}")
    
    # Get DES key and create cipher
    # LBBA-FLAG: Using Single DES for encryption
    # LBBA-FLAG: ECB does not provide semantic security (should use CBC or GCM)
    key = get_des_key()
    cipher = Cipher(algorithms.DES(key), modes.ECB())
    encryptor = cipher.encryptor()

    # Pad the data to be multiple of 8 (DES block size)
    pad_length = 8 - (len(file_content) % 8)
    padded_data = file_content + (bytes([pad_length]) * pad_length)
    
    # Encrypt the file
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    logger.info(f"Encrypted data, size: {len(encrypted_data)} bytes")

    # Upload to GCS with checksum metadata
    bucket = storage_client.bucket(os.environ['BUCKET_NAME'])
    blob = bucket.blob(file.filename)
    blob.metadata = {'sha1_checksum': sha1_hash}
    blob.upload_from_string(encrypted_data)
    logger.info(f"Uploaded encrypted file to GCS: {file.filename}")

    return f'File {file.filename} uploaded and encrypted successfully', 200 