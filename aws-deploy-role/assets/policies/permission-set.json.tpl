{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Sid": "TerraformStateBucket",
			"Effect": "Allow",
			"Action": [
				"s3:GetObject",
				"s3:PutObject",
				"s3:DeleteObject",
				"s3:ListBucket",
				"s3:GetBucketAcl",
				"s3:CreateBucket",
				"s3:PutBucketVersioning",
				"s3:PutEncryptionConfiguration",
				"s3:PutBucketPublicAccessBlock",
				"s3:PutBucketTagging"
			],
			"Resource": [
				"arn:aws:s3:::{{STATE_BUCKET}}",
				"arn:aws:s3:::{{STATE_BUCKET}}/*"
			]
		},
		{
			"Sid": "AssumeDeployRole",
			"Effect": "Allow",
			"Action": "sts:AssumeRole",
			"Resource": "arn:aws:iam::{{ACCOUNT_ID}}:role/{{PROJECT}}-deploy"
		},
		{
			"Sid": "ManageDeployRole",
			"Effect": "Allow",
			"Action": [
				"iam:CreateRole",
				"iam:GetRole",
				"iam:DeleteRole",
				"iam:TagRole",
				"iam:PutRolePolicy",
				"iam:GetRolePolicy",
				"iam:DeleteRolePolicy",
				"iam:ListRolePolicies",
				"iam:ListAttachedRolePolicies",
				"iam:AttachRolePolicy",
				"iam:DetachRolePolicy",
				"iam:UpdateAssumeRolePolicy"
			],
			"Resource": "arn:aws:iam::{{ACCOUNT_ID}}:role/{{PROJECT}}-deploy"
		},
		{
			"Sid": "ManageDeployPolicies",
			"Effect": "Allow",
			"Action": [
				"iam:CreatePolicy",
				"iam:DeletePolicy",
				"iam:GetPolicy",
				"iam:CreatePolicyVersion",
				"iam:DeletePolicyVersion",
				"iam:ListPolicyVersions",
				"iam:ListEntitiesForPolicy",
				"iam:TagPolicy",
				"iam:UntagPolicy"
			],
			"Resource": "arn:aws:iam::{{ACCOUNT_ID}}:policy/{{PROJECT}}-deploy-*"
		},
		{
			"Sid": "StsIdentity",
			"Effect": "Allow",
			"Action": "sts:GetCallerIdentity",
			"Resource": "*"
		}
	]
}
