#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") --role-name NAME --account-id ID --trust-policy FILE --policy-dir DIR [--profile PROFILE]

Idempotent create-or-update for an IAM deploy role with managed policies.

Options:
  --role-name      Name of the IAM role to create/update
  --account-id     AWS account ID
  --trust-policy   Path to trust policy JSON file
  --policy-dir     Directory containing managed policy JSON files
  --profile        AWS CLI profile (optional)
  -h, --help       Show this help
EOF
  exit 1
}

ROLE_NAME=""
ACCOUNT_ID=""
TRUST_POLICY=""
POLICY_DIR=""
PROFILE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role-name)     ROLE_NAME="$2"; shift 2 ;;
    --account-id)    ACCOUNT_ID="$2"; shift 2 ;;
    --trust-policy)  TRUST_POLICY="$2"; shift 2 ;;
    --policy-dir)    POLICY_DIR="$2"; shift 2 ;;
    --profile)       PROFILE_ARG="--profile $2"; shift 2 ;;
    -h|--help)       usage ;;
    *)               echo "Error: unknown option: $1" >&2; usage ;;
  esac
done

[[ -z "$ROLE_NAME" ]]    && { echo "Error: --role-name is required" >&2; usage; }
[[ -z "$ACCOUNT_ID" ]]   && { echo "Error: --account-id is required" >&2; usage; }
[[ -z "$TRUST_POLICY" ]] && { echo "Error: --trust-policy is required" >&2; usage; }
[[ -z "$POLICY_DIR" ]]   && { echo "Error: --policy-dir is required" >&2; usage; }
[[ ! -f "$TRUST_POLICY" ]] && { echo "Error: trust policy file not found: $TRUST_POLICY" >&2; exit 1; }
[[ ! -d "$POLICY_DIR" ]]   && { echo "Error: policy directory not found: $POLICY_DIR" >&2; exit 1; }

shopt -s nullglob
POLICY_FILES=("$POLICY_DIR"/*.json)
shopt -u nullglob

[[ ${#POLICY_FILES[@]} -eq 0 ]] && { echo "Error: no *.json files found in $POLICY_DIR" >&2; exit 1; }

IFS=$'\n' POLICY_FILES=($(sort <<<"${POLICY_FILES[*]}")); unset IFS

# --- Pre-flight validation ---
echo "=== Pre-flight validation ==="
ERRORS=0
for f in "${POLICY_FILES[@]}"; do
  fname=$(basename "$f")

  if ! python3 -c "import json,sys; json.load(sys.stdin)" < "$f" 2>/dev/null; then
    echo "FAIL  $fname — invalid JSON" >&2
    ERRORS=$((ERRORS + 1))
    continue
  fi

  SIZE=$(python3 -c "import urllib.parse,sys; print(len(urllib.parse.quote(sys.stdin.read())))" < "$f")
  if [[ $SIZE -ge 6144 ]]; then
    echo "FAIL  $fname — URL-encoded size ${SIZE} >= 6144" >&2
    ERRORS=$((ERRORS + 1))
  else
    echo "  OK  $fname (${SIZE}/6144)"
  fi
done

if [[ ${#POLICY_FILES[@]} -gt 10 ]]; then
  echo "WARN  ${#POLICY_FILES[@]} policy files — AWS default limit is 10 managed policies per role" >&2
fi

[[ $ERRORS -gt 0 ]] && { echo "Aborting: $ERRORS validation error(s)" >&2; exit 1; }
echo ""

# --- Role create/update ---
echo "=== Role ==="
# shellcheck disable=SC2086
if aws iam get-role --role-name "${ROLE_NAME}" $PROFILE_ARG >/dev/null 2>&1; then
  echo "Role ${ROLE_NAME} exists — updating trust policy..."
  # shellcheck disable=SC2086
  aws iam update-assume-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-document "file://${TRUST_POLICY}" \
    $PROFILE_ARG
else
  echo "Creating role ${ROLE_NAME}..."
  # shellcheck disable=SC2086
  aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document "file://${TRUST_POLICY}" \
    --tags Key=App,Value="${ROLE_NAME}" Key=ManagedBy,Value=archon \
    $PROFILE_ARG
fi

# shellcheck disable=SC2086
aws iam tag-role \
  --role-name "${ROLE_NAME}" \
  --tags Key=App,Value="${ROLE_NAME}" Key=ManagedBy,Value=archon \
  $PROFILE_ARG 2>/dev/null || true
echo ""

# --- Managed policy sync ---
echo "=== Managed policies ==="
DESIRED_POLICY_NAMES=()

for f in "${POLICY_FILES[@]}"; do
  STEM=$(basename "$f" .json)
  POLICY_NAME="${ROLE_NAME}-${STEM}"
  POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"
  DESIRED_POLICY_NAMES+=("$POLICY_NAME")

  # shellcheck disable=SC2086
  if aws iam get-policy --policy-arn "$POLICY_ARN" $PROFILE_ARG >/dev/null 2>&1; then
    echo "Updating ${POLICY_NAME}..."

    # shellcheck disable=SC2086
    VERSIONS=$(aws iam list-policy-versions --policy-arn "$POLICY_ARN" \
      --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text $PROFILE_ARG)

    VERSION_COUNT=$(echo "$VERSIONS" | wc -w | tr -d ' ')
    if [[ $VERSION_COUNT -ge 4 ]]; then
      OLDEST=$(echo "$VERSIONS" | tr '\t' '\n' | sort | head -1)
      echo "  Deleting oldest non-default version ${OLDEST}..."
      # shellcheck disable=SC2086
      aws iam delete-policy-version \
        --policy-arn "$POLICY_ARN" \
        --version-id "$OLDEST" \
        $PROFILE_ARG
    fi

    # shellcheck disable=SC2086
    aws iam create-policy-version \
      --policy-arn "$POLICY_ARN" \
      --policy-document "file://${f}" \
      --set-as-default \
      $PROFILE_ARG >/dev/null
  else
    echo "Creating ${POLICY_NAME}..."
    # shellcheck disable=SC2086
    aws iam create-policy \
      --policy-name "$POLICY_NAME" \
      --policy-document "file://${f}" \
      --tags Key=App,Value="${ROLE_NAME}" Key=ManagedBy,Value=archon \
      $PROFILE_ARG >/dev/null
  fi

  # shellcheck disable=SC2086
  ATTACHED=$(aws iam list-attached-role-policies --role-name "${ROLE_NAME}" \
    --query "AttachedPolicies[?PolicyArn=='${POLICY_ARN}'].PolicyArn" --output text $PROFILE_ARG)

  if [[ -z "$ATTACHED" ]]; then
    echo "  Attaching ${POLICY_NAME} to ${ROLE_NAME}..."
    # shellcheck disable=SC2086
    aws iam attach-role-policy \
      --role-name "${ROLE_NAME}" \
      --policy-arn "$POLICY_ARN" \
      $PROFILE_ARG
  fi
done
echo ""

# --- Orphan cleanup ---
echo "=== Orphan cleanup ==="
# shellcheck disable=SC2086
ATTACHED_ARNS=$(aws iam list-attached-role-policies --role-name "${ROLE_NAME}" \
  --query 'AttachedPolicies[].PolicyArn' --output text $PROFILE_ARG)

PREFIX="arn:aws:iam::${ACCOUNT_ID}:policy/${ROLE_NAME}-"
ORPHANS_FOUND=0

for ARN in $ATTACHED_ARNS; do
  [[ "$ARN" != ${PREFIX}* ]] && continue

  ATTACHED_NAME=${ARN#"arn:aws:iam::${ACCOUNT_ID}:policy/"}
  IS_DESIRED=false
  for DESIRED in "${DESIRED_POLICY_NAMES[@]}"; do
    [[ "$ATTACHED_NAME" == "$DESIRED" ]] && { IS_DESIRED=true; break; }
  done

  if [[ "$IS_DESIRED" == false ]]; then
    ORPHANS_FOUND=$((ORPHANS_FOUND + 1))

    # shellcheck disable=SC2086
    ENTITIES=$(aws iam list-entities-for-policy --policy-arn "$ARN" \
      --query 'length(PolicyRoles[])' --output text $PROFILE_ARG)

    if [[ "$ENTITIES" -gt 1 ]]; then
      echo "SKIP  ${ATTACHED_NAME} — attached to ${ENTITIES} roles, detaching from this role only"
      # shellcheck disable=SC2086
      aws iam detach-role-policy --role-name "${ROLE_NAME}" --policy-arn "$ARN" $PROFILE_ARG
    else
      echo "Removing orphan ${ATTACHED_NAME}..."
      # shellcheck disable=SC2086
      aws iam detach-role-policy --role-name "${ROLE_NAME}" --policy-arn "$ARN" $PROFILE_ARG

      # shellcheck disable=SC2086
      VERSIONS=$(aws iam list-policy-versions --policy-arn "$ARN" \
        --query 'Versions[?IsDefaultVersion==`false`].VersionId' --output text $PROFILE_ARG)
      for VID in $VERSIONS; do
        # shellcheck disable=SC2086
        aws iam delete-policy-version --policy-arn "$ARN" --version-id "$VID" $PROFILE_ARG
      done

      # shellcheck disable=SC2086
      aws iam delete-policy --policy-arn "$ARN" $PROFILE_ARG
    fi
  fi
done

[[ $ORPHANS_FOUND -eq 0 ]] && echo "No orphaned policies found."
echo ""

# --- Legacy inline cleanup ---
LEGACY_POLICY_NAME="${ROLE_NAME}Policy"
# shellcheck disable=SC2086
if aws iam get-role-policy --role-name "${ROLE_NAME}" --policy-name "${LEGACY_POLICY_NAME}" $PROFILE_ARG >/dev/null 2>&1; then
  echo "=== Legacy inline cleanup ==="
  echo "Deleting legacy inline policy ${LEGACY_POLICY_NAME}..."
  # shellcheck disable=SC2086
  aws iam delete-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-name "${LEGACY_POLICY_NAME}" \
    $PROFILE_ARG
  echo ""
fi

# --- Verification ---
echo "=== Verification ==="
# shellcheck disable=SC2086
ROLE_ARN=$(aws iam get-role --role-name "${ROLE_NAME}" --query 'Role.Arn' --output text $PROFILE_ARG)
echo "Role ARN: ${ROLE_ARN}"

echo ""
echo "Managed policies:"
# shellcheck disable=SC2086
aws iam list-attached-role-policies --role-name "${ROLE_NAME}" \
  --query 'AttachedPolicies[].PolicyName' --output table $PROFILE_ARG

# shellcheck disable=SC2086
INLINE=$(aws iam list-role-policies --role-name "${ROLE_NAME}" --query 'PolicyNames' --output text $PROFILE_ARG)
if [[ -n "$INLINE" ]]; then
  echo ""
  echo "WARNING: inline policies still present: ${INLINE}"
fi

echo ""
echo "Bootstrap complete. To assume this role:"
echo "  source ./assume-role.sh ${ROLE_NAME}"
