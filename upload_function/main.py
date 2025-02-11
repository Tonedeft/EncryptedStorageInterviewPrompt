import os
from google.cloud import storage
from google.cloud import secretmanager
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import functions_framework

# Initialize clients
storage_client = storage.Client()
secrets_client = secretmanager.SecretManagerServiceClient()

def get_des_key():
    """Retrieve DES key from Secret Manager"""
    name = f"projects/{os.environ['PROJECT_ID']}/secrets/des-key/versions/latest"
    response = secrets_client.access_secret_version(request={"name": name})
    return base64.b64decode(response.payload.data.decode())

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
        return 'Method not allowed', 405

    # Check if file is present in request
    if 'file' not in request.files:
        return 'No file provided', 400

    file = request.files['file']
    if file.filename == '':
        return 'No file selected', 400

    # Read file content
    file_content = file.read()
    
    # Get DES key and create cipher
    key = get_des_key()
    cipher = Cipher(algorithms.DES(key), modes.ECB())
    encryptor = cipher.encryptor()

    # Pad the data to be multiple of 8 (DES block size)
    pad_length = 8 - (len(file_content) % 8)
    padded_data = file_content + (bytes([pad_length]) * pad_length)
    
    # Encrypt the file
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

    # Upload to GCS
    bucket = storage_client.bucket(os.environ['BUCKET_NAME'])
    blob = bucket.blob(file.filename)
    blob.upload_from_string(encrypted_data)

    return f'File {file.filename} uploaded and encrypted successfully', 200 