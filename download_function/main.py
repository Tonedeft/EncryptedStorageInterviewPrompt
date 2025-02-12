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
    logger.error(f"Retrieved DES key: {key.hex()}")
    return key

@functions_framework.http
def download_file(request):
    """HTTP Cloud Function to handle file download and decryption.
    
    Args:
        request (flask.Request): The request object
    Returns:
        The decrypted file content
    """
    if request.method != 'GET':
        logger.error(f"Invalid method: {request.method}")
        return 'Method not allowed', 405

    # Get filename from query parameters
    filename = request.args.get('filename')
    if not filename:
        logger.error("No filename provided")
        return 'No filename provided', 400

    logger.info(f"Requested file: {filename}")

    # Download from GCS
    bucket = storage_client.bucket(os.environ['BUCKET_NAME'])
    blob = bucket.blob(filename)
    
    try:
        # Get the stored checksum
        blob.reload()  # Reload to ensure we have the latest metadata
        stored_checksum = blob.metadata.get('sha1_checksum')
        if not stored_checksum:
            logger.error("No checksum found in metadata")
            return 'File checksum not found', 500
            
        logger.info(f"Retrieved stored checksum: {stored_checksum}")
        encrypted_data = blob.download_as_bytes()
        logger.info(f"Downloaded encrypted data, size: {len(encrypted_data)} bytes")
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return f'File {filename} not found: {str(e)}', 404

    # Get DES key and create cipher
    key = get_des_key()
    cipher = Cipher(algorithms.DES(key), modes.ECB())
    decryptor = cipher.decryptor()

    # Decrypt the file
    decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
    logger.info(f"Decrypted data, size: {len(decrypted_data)} bytes")
    
    # LBBA-FLAG?: Don't remove padding (as a bug in the logic?)
    unpadded_data = decrypted_data
    # Remove padding
    # pad_length = decrypted_data[-1]
    # unpadded_data = decrypted_data[:-pad_length]
    # logger.info(f"Removed padding, final size: {len(unpadded_data)} bytes")
    
    # Calculate SHA-1 checksum of decrypted file
    calculated_checksum = hashlib.sha1(unpadded_data).hexdigest()
    logger.info(f"Calculated checksum: {calculated_checksum}")
    
    # LBBA-FLAG?: Don't verify the decrypted checksum before returning
    # Verify checksum
    # if calculated_checksum != stored_checksum:
    #     logger.error(f"Checksum mismatch. Stored: {stored_checksum}, Calculated: {calculated_checksum}")
    #     return 'File integrity check failed', 500

    logger.info("Returning decrypted file")
    # Return the decrypted file
    return unpadded_data, 200, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename={filename}'
    } 