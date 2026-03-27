output "backend_ecr_url" {
  description = "ECR repository URL for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_url" {
  description = "ECR repository URL for the frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "deploy_role_arn" {
  description = "ARN of the IAM role used by CI/CD to push images and update ECS"
  value       = aws_iam_role.deploy.arn
}

output "backend_url" {
  description = "ALB DNS name — backend API endpoint"
  value       = "http://${aws_lb.main.dns_name}"
}

output "frontend_url" {
  description = "CloudFront domain — frontend URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name (used in CD workflow)"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name (used in CD workflow)"
  value       = aws_ecs_service.backend.name
}
