#!/usr/bin/env bash

helm upgrade --install crossplane \
     --namespace crossplane-system \
     --create-namespace crossplane-stable/crossplane \
     --version v2.0.2 \
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

#  package: ghcr.io/crossplane-contrib/function-pythonic:v0.0.0-20250819201108-49cfb066579f
#  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.2.1

kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1
kind: Function
metadata:
  name: function-pythonic
spec:
  package: xpkg.upbound.io/crossplane-contrib/function-pythonic:v0.2.1
  runtimeConfigRef:
    apiVersion: pkg.crossplane.io/v1beta1
    kind: DeploymentRuntimeConfig
    name: function-pythonic
EOF
