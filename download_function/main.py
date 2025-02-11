import os
from google.cloud import storage
from google.cloud import secretmanager
import base64
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
def download_file(request):
    """HTTP Cloud Function to handle file download and decryption.
    
    Args:
        request (flask.Request): The request object
    Returns:
        The decrypted file content
    """
    if request.method != 'GET':
        return 'Method not allowed', 405

    # Get filename from query parameters
    filename = request.args.get('filename')
    if not filename:
        return 'No filename provided', 400

    # Download from GCS
    bucket = storage_client.bucket(os.environ['BUCKET_NAME'])
    blob = bucket.blob(filename)
    
    try:
        encrypted_data = blob.download_as_bytes()
    except Exception:
        return f'File {filename} not found', 404

    # Get DES key and create cipher
    key = get_des_key()
    cipher = Cipher(algorithms.DES(key), modes.ECB())
    decryptor = cipher.decryptor()

    # Decrypt the file
    decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
    
    # Remove padding
    pad_length = decrypted_data[-1]
    unpadded_data = decrypted_data[:-pad_length]

    # Return the decrypted file
    return unpadded_data, 200, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename={filename}'
    } 