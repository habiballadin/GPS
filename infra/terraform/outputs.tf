output "elastic_ip" {
  description = "Configure GPS devices to use this public IP."
  value       = aws_eip.app.public_ip
}

output "teltonika_tcp_endpoint" {
  value = "${aws_eip.app.public_ip}:5001"
}

output "concox_tcp_endpoint" {
  value = "${aws_eip.app.public_ip}:5002"
}

output "api_url" {
  value = "http://${aws_eip.app.public_ip}"
}
