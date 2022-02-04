import moto.cloudwatch.responses as cloudwatch_responses
from moto.cloudwatch.models import FakeAlarm

from localstack import config
from localstack.services.infra import start_moto_server
from localstack.utils.aws import aws_stack
from localstack.utils.patch import patch


def apply_patches():
    if "<TreatMissingData>" not in cloudwatch_responses.DESCRIBE_ALARMS_TEMPLATE:
        cloudwatch_responses.DESCRIBE_ALARMS_TEMPLATE = (
            cloudwatch_responses.DESCRIBE_ALARMS_TEMPLATE.replace(
                "</AlarmName>",
                "</AlarmName><TreatMissingData>{{ alarm.treat_missing_data }}</TreatMissingData>",
            )
        )

    # add put_composite_alarm

    def put_composite_alarm(self):
        return self.put_metric_alarm()

    if not hasattr(cloudwatch_responses.CloudWatchResponse, "put_composite_alarm"):
        cloudwatch_responses.CloudWatchResponse.put_composite_alarm = put_composite_alarm

    @patch(target=FakeAlarm.update_state)
    def update_state(target, self, reason, reason_data, state_value):
        target(self, reason, reason_data, state_value)

        # check the state and trigger required actions
        if self.actions_enabled:
            actions = None
            if self.state_value == "OK":
                actions = self.ok_actions
            elif self.state_value == "ALARM":
                actions = self.alarm_actions
            else:
                actions = self.insufficient_data_actions
            for action in actions:
                data = aws_stack.parse_arn(action)
                # test for sns - can this be done in a more generic way?
                if data["service"] == "sns":
                    service = aws_stack.connect_to_service(data["service"])
                    # publish this way? what should go into subject/message etc?
                    service.publish(TopicArn=action, Subject=self.name, Message=self.description)
            # log warning -> not supported + add todo


def start_cloudwatch(port=None, asynchronous=False, update_listener=None):
    port = port or config.service_port("cloudwatch")
    apply_patches()
    return start_moto_server(
        "cloudwatch",
        port,
        name="CloudWatch",
        update_listener=update_listener,
        asynchronous=asynchronous,
    )
