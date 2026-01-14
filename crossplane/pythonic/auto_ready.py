

def process(composite):
    for name, resource in composite.resources:
        if resource.observed:
            if resource.autoReady or (resource.autoReady is None and composite.autoReady):
                if resource.ready is None:
                    if _checks.get((resource.apiVersion, resource.kind), _check_default).ready(resource):
                        resource.ready = True


class ConditionReady:
    def ready(self, resource):
        return bool(resource.conditions.Ready.status)

_checks = {}
_check_default = ConditionReady()

class Check:
    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'apiVersion'):
            _checks[(cls.apiVersion, cls.__name__)] = cls()

    def ready(self, resource):
        raise NotImplementedError()

class AlwaysReady(Check):
    def ready(self, resource):
        return True


class ClusterRole(AlwaysReady):
    apiVersion = 'rbac.authorization.k8s.io/v1'

class ClusterRoleBinding(AlwaysReady):
    apiVersion = 'rbac.authorization.k8s.io/v1'

class ConfigMap(AlwaysReady):
    apiVersion = 'v1'

class CronJob(Check):
    apiVersion = 'batch/v1'
    def ready(self, resource):
        if resource.observed.spec.suspend and len(resource.observed.spec.suspend):
            return True
        if not resource.status.lastScheduleTime:
            return False
        if resource.status.active:
            return True
        if not resource.status.lastSuccessfulTime:
            return False
        return str(resource.status.lastSuccessfulTime) >= str(resource.status.lastScheduleTime)

class DaemonSet(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        if not resource.status.desiredNumberScheduled:
            return False
        scheduled = resource.status.desiredNumberScheduled
        return (scheduled == resource.status.numberReady and
                scheduled == resource.status.updatedNumberScheduled and
                scheduled == resource.status.numberAvailable
                )

class Deployment(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        replicas = resource.observed.spec.replicas or 1
        if resource.status.updatedReplicas != replicas or resource.status.availableReplicas != replicas:
            return False
        return bool(resource.conditions.Available.status)

class HorizontalPodAutoscaler(Check):
    apiVersion = 'autoscaling/v2'
    def ready(self, resource):
        for type in ('FailedGetScale', 'FailedUpdateScale', 'FailedGetResourceMetric', 'InvalidSelector'):
            if resource.conditions[type].status:
                return False
        for type in ('ScalingActive', 'ScalingLimited'):
            if resource.conditions[type].status:
                return True
        return False

class Ingress(Check):
    apiVersion = 'networking.k8s.io/v1'
    def ready(self, resource):
        return len(resource.status.loadBalancer.ingress) > 0

class Job(Check):
    apiVersion = 'batch/v1'
    def ready(self, resource):
        for type in ('Failed', 'Suspended'):
            if resource.conditions[type].status:
                return False
        return bool(resource.conditions.Complete.status)

class Namespace(AlwaysReady):
    apiVersion = 'v1'

class PersistentVolumeClaim(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        return resource.status.phase == 'Bound'

class Pod(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if resource.status.phase == 'Succeeded':
            return True
        if resource.status.phase == 'Running':
            if resource.observed.spec.restartPolicy == 'Always':
                if resource.conditions.Ready.status:
                    return True
        return False

class ReplicaSet(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if int(resource.status.observedGeneration) < int(resource.observed.metadata.generation):
            return False
        if resource.conditions.ReplicaFailure.status:
            return False
        return int(resource.status.availableReplicas) >= int(resource.observed.spec.replicas or 1)

class Role(AlwaysReady):
    apiVersion = 'rbac.authorization.k8s.io/v1'

class RoleBinding(AlwaysReady):
    apiVersion = 'rbac.authorization.k8s.io/v1'

class Secret(AlwaysReady):
    apiVersion = 'v1'

class Service(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if resource.observed.spec.type != 'LoadBalancer':
            return True
        return len(resource.status.loadBalancer.ingress) > 0

class ServiceAccount(AlwaysReady):
    apiVersion = 'v1'

class StatefulSet(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        replicas = resource.observed.spec.replicas or 1
        return (resource.status.readyReplicas == replicas and
                resource.status.currentReplicas == replicas and
                resource.status.currentRevision == resource.status.updateRevision
                )
