output "upload_function_url" {
  value = google_cloudfunctions2_function.upload_function.url
}

output "download_function_url" {
  value = google_cloudfunctions2_function.download_function.url
} 