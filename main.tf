# Configure the Google Cloud provider
provider "google" {
  project = var.project_id
  region  = var.region
}

# Create a GCS bucket for storing encrypted files
resource "google_storage_bucket" "encrypted_files" {
  name     = "${var.project_id}-encrypted-files"
  location = var.region
  
  uniform_bucket_level_access = true
  
  versioning {
    enabled = true
  }
}

# Create a service account for the cloud functions
resource "google_service_account" "function_account" {
  account_id   = "encrypted-files-function"
  display_name = "Service Account for Encrypted Files Functions"
}

# Grant the service account access to the bucket
resource "google_storage_bucket_iam_member" "function_bucket_access" {
  bucket = google_storage_bucket.encrypted_files.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.function_account.email}"
}

# Create a secret for the DES key with hardcoded value
resource "google_secret_manager_secret" "des_key" {
  secret_id = "des-key"
  
  replication {
    auto {}
  }
}

# Add the secret version with hardcoded DES key
resource "google_secret_manager_secret_version" "des_key_version" {
  secret      = google_secret_manager_secret.des_key.id
  # Using a hardcoded 8-byte key "12345678" (base64 encoded)
  secret_data = "MTIzNDU2Nzg="  # base64 encoded value of "12345678"
}

# Grant the service account access to the secret
resource "google_secret_manager_secret_iam_member" "secret_access" {
  secret_id = google_secret_manager_secret.des_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.function_account.email}"
}

# Upload function
resource "google_storage_bucket_object" "upload_function_zip" {
  name   = "upload-function-${data.archive_file.upload_function.output_md5}.zip"
  bucket = google_storage_bucket.encrypted_files.name
  source = data.archive_file.upload_function.output_path
}

resource "google_cloudfunctions2_function" "upload_function" {
  name        = "upload-encrypted-file"
  location    = var.region
  description = "Function to upload and encrypt files"

  build_config {
    runtime     = "python310"
    entry_point = "upload_file"
    source {
      storage_source {
        bucket = google_storage_bucket.encrypted_files.name
        object = google_storage_bucket_object.upload_function_zip.name
      }
    }
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 60
    
    environment_variables = {
      PROJECT_ID  = var.project_id
      BUCKET_NAME = google_storage_bucket.encrypted_files.name
    }
    
    service_account_email = google_service_account.function_account.email
  }
}

# Download function
resource "google_storage_bucket_object" "download_function_zip" {
  name   = "download-function-${data.archive_file.download_function.output_md5}.zip"
  bucket = google_storage_bucket.encrypted_files.name
  source = data.archive_file.download_function.output_path
}

resource "google_cloudfunctions2_function" "download_function" {
  name        = "download-encrypted-file"
  location    = var.region
  description = "Function to download and decrypt files"

  build_config {
    runtime     = "python310"
    entry_point = "download_file"
    source {
      storage_source {
        bucket = google_storage_bucket.encrypted_files.name
        object = google_storage_bucket_object.download_function_zip.name
      }
    }
  }

  service_config {
    max_instance_count = 1
    available_memory   = "256M"
    timeout_seconds    = 60
    
    environment_variables = {
      PROJECT_ID  = var.project_id
      BUCKET_NAME = google_storage_bucket.encrypted_files.name
    }
    
    service_account_email = google_service_account.function_account.email
  }
}

# Data source for zipping functions
data "archive_file" "upload_function" {
  type        = "zip"
  output_path = "/tmp/upload_function.zip"
  source_dir  = "${path.module}/upload_function"
}

data "archive_file" "download_function" {
  type        = "zip"
  output_path = "/tmp/download_function.zip"
  source_dir  = "${path.module}/download_function"
} 