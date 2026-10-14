#!/usr/bin/env bash
# Destroy the temporary `loadtest` environment once its ttl tag has passed.
#
#   scripts/loadtest-teardown.sh [--force] [--dry-run]
#
# The target is hard-coded: this script cannot destroy any other environment.
# Needs AWS credentials, terraform, and the aws CLI, plus:
#   TF_STATE_BUCKET, TF_STATE_KMS_KEY_ARN   backend settings (see bootstrap outputs)
#   TF_VAR_domain, TF_VAR_alert_emails      the environment's variables
#   AWS_REGION                              defaults to eu-central-1
set -euo pipefail

readonly ENVIRONMENT=loadtest
readonly NAME="opspilot-${ENVIRONMENT}"
readonly STATE_KEY="opspilot/${ENVIRONMENT}/terraform.tfstate"
export AWS_REGION="${AWS_REGION:-eu-central-1}"

force=false
dry_run=false
for arg in "$@"; do
  case "$arg" in
    --force) force=true ;;
    --dry-run) dry_run=true ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "$0")/.." && pwd)/infrastructure/terraform/environments/${ENVIRONMENT}"
tf() { terraform -chdir="$root" "$@"; }

# Guard: the configuration must really be the loadtest composition.
grep -q "key *= *\"${STATE_KEY}\"" "$root/main.tf" || { echo "refusing: $root does not use state key ${STATE_KEY}" >&2; exit 1; }
grep -q "environment *= *\"${ENVIRONMENT}\"" "$root/main.tf" || { echo "refusing: $root is not the ${ENVIRONMENT} environment" >&2; exit 1; }

# The earliest ttl among the environment's tagged resources.
# shellcheck disable=SC2016 # backticks are JMESPath literals, not shell
ttl="$(aws resourcegroupstaggingapi get-resources \
  --tag-filters "Key=project,Values=opspilot" "Key=environment,Values=${ENVIRONMENT}" \
  --query 'ResourceTagMappingList[].Tags[?Key==`ttl`].Value[]' --output text | tr '\t' '\n' | grep -v '^$' | sort | head -n1 || true)"

if [ -z "$ttl" ]; then
  echo "no ${ENVIRONMENT} environment found (no resources tagged environment=${ENVIRONMENT} with a ttl)"
  exit 0
fi

now="$(date -u +%s)"
expires="$(date -u -d "$ttl" +%s)"
if [ "$now" -lt "$expires" ] && [ "$force" = false ]; then
  echo "${ENVIRONMENT} expires at ${ttl}; keeping it"
  exit 0
fi
echo "${ENVIRONMENT} ttl ${ttl}, force=${force}: destroying"
if [ "$dry_run" = true ]; then
  echo "dry run: stopping before any change"
  exit 0
fi

: "${TF_STATE_BUCKET:?set TF_STATE_BUCKET}"
: "${TF_STATE_KMS_KEY_ARN:?set TF_STATE_KMS_KEY_ARN}"
export TF_VAR_expires_at="$ttl" TF_IN_AUTOMATION=1

tf init -input=false \
  -backend-config="bucket=${TF_STATE_BUCKET}" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="kms_key_id=${TF_STATE_KMS_KEY_ARN}"

# 1. Helm releases live inside the cluster that is about to go, behind a
#    private API endpoint this runner cannot reach: forget them.
tf state list | grep -E '(^|\.)helm_release\.' | while read -r address; do
  tf state rm "$address"
done

# 2. Delete the cluster first, so Karpenter and the load balancer controller
#    stop creating resources.
tf destroy -input=false -auto-approve -target=module.environment.module.eks.aws_eks_cluster.this

# 3. Remove what those controllers created outside Terraform; it would block
#    deleting the VPC and the node role.
instances="$(aws ec2 describe-instances \
  --filters "Name=tag:eks:eks-cluster-name,Values=${NAME}" "Name=tag-key,Values=karpenter.sh/nodepool" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)"
if [ -n "$instances" ]; then
  # shellcheck disable=SC2086 # word splitting intended: one argument per instance
  aws ec2 terminate-instances --instance-ids $instances >/dev/null
  # shellcheck disable=SC2086
  aws ec2 wait instance-terminated --instance-ids $instances
fi

for profile in $(aws iam list-instance-profiles-for-role --role-name "${NAME}-karpenter-node" \
  --query 'InstanceProfiles[].InstanceProfileName' --output text 2>/dev/null || true); do
  aws iam remove-role-from-instance-profile --instance-profile-name "$profile" --role-name "${NAME}-karpenter-node"
  aws iam delete-instance-profile --instance-profile-name "$profile"
done

by_cluster_tag() {
  aws resourcegroupstaggingapi get-resources --resource-type-filters "$1" \
    --tag-filters "Key=elbv2.k8s.aws/cluster,Values=${NAME}" \
    --query 'ResourceTagMappingList[].ResourceARN' --output text
}
for lb in $(by_cluster_tag elasticloadbalancing:loadbalancer); do
  aws elbv2 delete-load-balancer --load-balancer-arn "$lb"
  aws elbv2 wait load-balancers-deleted --load-balancer-arns "$lb"
done
for tg in $(by_cluster_tag elasticloadbalancing:targetgroup); do
  aws elbv2 delete-target-group --target-group-arn "$tg"
done
for sg in $(aws ec2 describe-security-groups --filters "Name=tag:elbv2.k8s.aws/cluster,Values=${NAME}" \
  --query 'SecurityGroups[].GroupId' --output text); do
  # Load balancer network interfaces take a moment to disappear.
  for _ in 1 2 3 4 5 6; do
    if aws ec2 delete-security-group --group-id "$sg"; then break; fi
    sleep 20
  done
done

# 4. Everything else.
tf destroy -input=false -auto-approve
echo "${ENVIRONMENT} destroyed"
