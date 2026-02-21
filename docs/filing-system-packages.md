# Filing System Packages


Composition Composite implementations can be coded in a stand alone python files
by configuring the function-pythonic deployment with the code mounted into
the package-runtime container, and then adding the mount point to the python
path using the --python-path command line option.
```yaml
apiVersion: pkg.crossplane.io/v1beta1
kind: DeploymentRuntimeConfig
metadata:
  name: function-pythonic
spec:
  deploymentTemplate:
    spec:
      template:
        spec:
          containers:
          - name: package-runtime
            args:
            - --debug
            - --python-path
            - /mnt/composites
            volumeMounts:
            - name: composites
              mountPath: /mnt/composites
          volumes:
          - name: composites
            configMap:
              name: pythonic-composites
```
See the [filing-system](examples/filing-system) example.
