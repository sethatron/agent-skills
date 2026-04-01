#!/usr/bin/env bash
# Usage: source ./assume-role.sh <role-name> [account-id] [session-name]
#    or: eval $(./assume-role.sh <role-name> [account-id] [session-name])

ROLE_NAME="${1:-}"
ACCOUNT_ID="${2:-}"
SESSION_NAME="${3:-}"

if [ -z "$ROLE_NAME" ]; then
    echo "Usage: source ./assume-role.sh <role-name> [account-id] [session-name]" >&2
    return 1 2>/dev/null || exit 1
fi

if [ -z "$ACCOUNT_ID" ]; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
        echo "Failed to determine AWS account ID. Are you authenticated?" >&2
        return 1 2>/dev/null || exit 1
    }
fi

if [ -z "$SESSION_NAME" ]; then
    SESSION_NAME="${ROLE_NAME}-session"
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

CREDS_JSON=$(aws sts assume-role \
    --role-arn "$ROLE_ARN" \
    --role-session-name "$SESSION_NAME" \
    --external-id "$ROLE_NAME" \
    --output json 2>&1) || {
    echo "Failed to assume role: ${ROLE_ARN}" >&2
    echo "$CREDS_JSON" >&2
    return 1 2>/dev/null || exit 1
}

AWS_ACCESS_KEY_ID=$(echo "$CREDS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['AccessKeyId'])")
AWS_SECRET_ACCESS_KEY=$(echo "$CREDS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['SecretAccessKey'])")
AWS_SESSION_TOKEN=$(echo "$CREDS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['Credentials']['SessionToken'])")

if [ "${BASH_SOURCE[0]:-}" = "${0}" ]; then
    echo "export AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
    echo "export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
    echo "export AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}"
else
    export AWS_ACCESS_KEY_ID
    export AWS_SECRET_ACCESS_KEY
    export AWS_SESSION_TOKEN
    echo "Assumed role: ${ROLE_ARN}" >&2
    echo "Session: ${SESSION_NAME}" >&2
fi
