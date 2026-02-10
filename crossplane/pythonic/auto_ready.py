
def resource_ready(resource):
    if not resource.observed:
        return None
    return _checks.get((resource.observed.apiVersion, resource.observed.kind), _check_default).ready(resource)


class ReadyCondition:
    def ready(self, resource):
        ready = resource.conditions.Ready
        if not ready._find_condition():
            return None
        if ready.status:
            return resource.observed.metadata.name
        if ready.reason:
            return resource.status.notReadyCondition[ready.reason]
        return resource.status.notReadyCondition

_checks = {}
_check_default = ReadyCondition()

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
        return resource.observed.metadata.name


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
            return resource.observed.metadata.name
        if not resource.status.lastScheduleTime:
            return resource.status.lastScheduleTime
        if resource.status.active:
            return resource.observed.metadata.name
        if not resource.status.lastSuccessfulTime:
            return resource.status.lastSuccessfulTime
        if str(resource.status.lastSuccessfulTime) < str(resource.status.lastScheduleTime):
            return resource.status.successfulBeforeSchedule
        return resource.observed.metadata.name

class DaemonSet(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        scheduled = resource.status.desiredNumberScheduled
        if not scheduled:
            return scheduled
        for field in ('numberReady', 'updatedNumberScheduled', 'numberAvailable'):
            value = resource.status[field]
            if not value:
                return value
            if scheduled != value:
                return resource.status[f"{field}NotScheduled"]
        return resource.observed.metadata.name

class Deployment(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        replicas = resource.observed.spec.replicas or 1
        for field in ('updatedReplicas', 'availableReplicas'):
            value = resource.status[field]
            if not value:
                return value
            if replicas != value:
                return resource.status[F"{field}NotReplicas"]
        available = resource.conditions.Available
        if not available:
            return resource.status.notAvailable
        if not available.status:
            if available.reason:
                return resource.status.notAvailable[available.reason]
            return resource.status.notAvailable
        return resource.observed.metadata.name

class HorizontalPodAutoscaler(Check):
    apiVersion = 'autoscaling/v2'
    def ready(self, resource):
        for type in ('FailedGetScale', 'FailedUpdateScale', 'FailedGetResourceMetric', 'InvalidSelector'):
            if resource.conditions[type].status:
                return resource.status[f"is{type}"]
        for type in ('ScalingActive', 'ScalingLimited'):
            if resource.conditions[type].status:
                return resource.observed.metadata.name
        return resource.status.notScalingActiveOrLimiited

class Ingress(Check):
    apiVersion = 'networking.k8s.io/v1'
    def ready(self, resource):
        if not len(resource.status.loadBalancer.ingress):
            return resource.status.noLoadBalanceIngresses
        return resource.observed.metadata.name

class Job(Check):
    apiVersion = 'batch/v1'
    def ready(self, resource):
        for type in ('Failed', 'Suspended'):
            if resource.conditions[type].status:
                return resource.status[f"is{type}"]
        complete = resource.conditions.Complete
        if not complete:
            return resource.status.notComplete
        if not complete.status:
            if complete.reason:
                return resource.status.notComplete[complete.reason]
            return resource.status.notComplete
        return resource.observed.metadata.name

class Namespace(AlwaysReady):
    apiVersion = 'v1'

class PersistentVolumeClaim(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if resource.status.phase != 'Bound':
            return resource.status.phaseNotBound
        return resource.observed.metadata.name

class Pod(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if resource.status.phase == 'Succeeded':
            return resource.observed.metadata.name
        if resource.status.phase == 'Running':
            if resource.observed.spec.restartPolicy == 'Always':
                if resource.conditions.Ready.status:
                    return resource.observed.metadata.name
        return resource.status.notSucceededOrRunning

class ReplicaSet(Check):
    apiVersion = 'v1'
    def ready(self, resource):
        if int(resource.status.observedGeneration) < int(resource.observed.metadata.generation):
            return resource.status.priorObservedGeneration
        if resource.conditions.ReplicaFailure.status:
            if resource.conditions.ReplicaFailure.reason:
                return resource.status.isReplicaFailure[resource.conditions.ReplicaFailure.reason]
            return resource.status.isReplicaFailure
        if int(resource.status.availableReplicas) < int(resource.observed.spec.replicas or 1):
            return resource.status.tooFewavailableReplicas
        return resource.observed.metadata.name

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
            return resource.observed.metadata.name
        if not len(resource.status.loadBalancer.ingress):
            return resource.status.noLoadBalancerIngresses
        return resource.observed.metadata.name

class ServiceAccount(AlwaysReady):
    apiVersion = 'v1'

class StatefulSet(Check):
    apiVersion = 'apps/v1'
    def ready(self, resource):
        replicas = resource.observed.spec.replicas or 1
        for field in ('readyReplicas', 'currentReplicas'):
            value = resource.status[field]
            if not value:
                return value
            if replicas != value:
                return resource.status[F"{field}NotReplicas"]
        if resource.status.currentRevision != resource.status.updateRevision:
            return resource.status.currentRevisionNotUpdateReivsion
        return resource.observed.metadata.name
