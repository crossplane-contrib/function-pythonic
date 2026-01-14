#!/usr/bin/env bash

cd $(dirname $0)

helm upgrade --install crossplane \
     --namespace crossplane-system \
     --create-namespace crossplane-stable/crossplane \
     --version v2.1.3 \
     --set 'args={--enable-realtime-compositions=false,--debug}'

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: provider-incluster
spec:
  deploymentTemplate:
    spec:
      selector: {}
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
          serviceAccountName: provider-incluster
  serviceAccountTemplate:
    metadata:
      name: provider-incluster
EOF

kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: provider-incluster
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-admin
subjects:
- kind: ServiceAccount
  name: provider-incluster
  namespace: crossplane-system
EOF

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-helm
spec:
  package: xpkg.crossplane.io/crossplane-contrib/provider-helm:v1.0.2
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: provider-incluster
EOF

kubectl apply -f - <<EOF
apiVersion: helm.m.crossplane.io/v1beta1
kind: ProviderConfig
metadata:
  namespace: crossplane-system
  name: default
spec:
  credentials:
    source: InjectedIdentity
EOF

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-kubernetes
spec:
  package: xpkg.crossplane.io/crossplane-contrib/provider-kubernetes:v1.0.0
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: provider-incluster
EOF

kubectl apply -f - <<EOF
apiVersion: kubernetes.m.crossplane.io/v1alpha1
kind: ProviderConfig
metadata:
  namespace: crossplane-system
  name: default
spec:
  credentials:
    source: InjectedIdentity
EOF

kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: function-pythonic
rules:
# Framework: posting the events about the handlers progress/errors.
- apiGroups:
  - ''
  resources:
  - events
  verbs:
  - create
# Application: read-only access for watching cluster-wide.
- apiGroups:
  - ''
  resources:
  - configmaps
  - secrets
  verbs:
  - list
  - watch
  - patch
EOF

kubectl apply -f - <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: function-pythonic
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: function-pythonic
subjects:
- kind: ServiceAccount
  namespace: crossplane-system
  name: function-pythonic
EOF

# kubectl delete -f - <<EOF
# apiVersion: rbac.authorization.k8s.io/v1
# kind: Role
# metadata:
#   namespace: crossplane-system
#   name: function-pythonic
# rules:
# # Framework: posting the events about the handlers progress/errors.
# - apiGroups:
#   - ''
#   resources:
#   - events
#   verbs:
#   - create
# # Application: watching & handling for the custom resource we declare.
# - apiGroups:
#   - ''
#   resources:
#   - configmaps
#   - secrets
#   verbs:
#   - list
#   - watch
#   - patch
# EOF

# kubectl delete -f - <<EOF
# apiVersion: rbac.authorization.k8s.io/v1
# kind: RoleBinding
# metadata:
#   namespace: crossplane-system
#   name: function-pythonic
# roleRef:
#   apiGroup: rbac.authorization.k8s.io
#   kind: Role
#   name: function-pythonic
# subjects:
# - kind: ServiceAccount
#   namespace: crossplane-system
#   name: function-pythonic
# EOF

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      selector: {}
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --packages
            - --pip-install
            - aiobotocore==v2.24.2
          serviceAccountName: function-pythonic
  serviceAccountTemplate:
    metadata:
      name: function-pythonic
EOF

#  package: ghcr.io/iciclespider/function-pythonic:v0.0.0-20260115045752-3c0cf4ebffd2
#  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.3.0

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: ghcr.io/iciclespider/function-pythonic:v0.0.0-20260115045752-3c0cf4ebffd2
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: function-pythonic
EOF

awsAccount=277707108430 # GP Dev/Sandbox
ssoRole=AdministratorPermSetBoundary

if [[ -f .aws-credentials ]]
then
    credentials=$(<.aws-credentials)
else
    client=$(aws --region=us-east-2 sso-oidc register-client --client-name=local-cloudops --client-type=public)
    id=$(echo "$client" | jq -r .clientId)
    secret=$(echo "$client" | jq -r .clientSecret)
    authorization=$(aws --region=us-east-2 sso-oidc start-device-authorization --client-id=$id --client-secret=$secret --start-url=https://helpsystems.awsapps.com/start)
    code=$(echo "$authorization" | jq -r .deviceCode)
    echo -n 'Waiting for authorization...'
    open -a 'Google Chrome' -n --args -incognito $(echo "$authorization" | jq -r .verificationUriComplete)
    while :
    do
        if response=$(aws --region=us-east-2 sso-oidc create-token --client-id=$id --client-secret=$secret --grant-type=urn:ietf:params:oauth:grant-type:device_code --device-code=$code 2>&1)
        then
            token=$(echo "$response" | jq -r .accessToken)
            break
        fi
        if ! [[ "$response" =~ [(]AuthorizationPendingException[)] ]]
        then
            echo
            echo "$response"
            exit 1
        fi
        echo -n '.'
        sleep 1
    done
    echo
    credentials=$(aws --region=us-east-2 sso get-role-credentials --account-id=$awsAccount --role-name=$ssoRole --access-token=$token | jq .roleCredentials)
    echo -n "$credentials" >.aws-credentials
fi

kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  namespace: crossplane-system
  name: aws-credentials
stringData:
  access-key-id: $(echo "$credentials" | jq -r .accessKeyId)
  secret-access-key: $(echo "$credentials" | jq -r .secretAccessKey)
  session-token: $(echo "$credentials" | jq -r .sessionToken)
  credentials: |
    [default]
    aws_access_key_id = $(echo "$credentials" | jq -r .accessKeyId)
    aws_secret_access_key = $(echo "$credentials" | jq -r .secretAccessKey)
    aws_session_token = $(echo "$credentials" | jq -r .sessionToken)
EOF

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Provider
metadata:
  name: provider-family-iam
spec:
  package: xpkg.upbound.io/upbound/provider-aws-iam:v2.3.0
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: provider-incluster
EOF

kubectl apply -f - <<EOF
apiVersion: aws.m.upbound.io/v1beta1
kind: ClusterProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-credentials
      key: credentials
EOF
