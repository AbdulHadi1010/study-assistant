"""Deploy the CloudFormation stack (table, secret, Lambda, roles) and save its outputs.

Asks for your Todoist token on the first deploy (hidden input). On later deploys
you can press Enter to keep the token already stored. Uses a CloudFormation
change set, so running it twice is safe: with no changes it just says so.
"""
import getpass
import subprocess
import sys

import boto3
from botocore.exceptions import ClientError, WaiterError

from common import ROOT, check_todoist_token, load_config, save_config

TEMPLATE = ROOT / "infra" / "template.yaml"
OUTPUT_TO_CONFIG = {
    "TableName": "table_name",
    "LambdaFunctionName": "lambda_function_name",
    "TodoistSecretArn": "todoist_secret_arn",
}


def stack_exists(cfn, stack_name: str) -> bool:
    try:
        status = cfn.describe_stacks(StackName=stack_name)["Stacks"][0]["StackStatus"]
    except ClientError:
        return False
    if status == "ROLLBACK_COMPLETE":  # a failed first create; it can only be deleted
        print("Previous attempt failed; deleting the broken stack first ...")
        cfn.delete_stack(StackName=stack_name)
        cfn.get_waiter("stack_delete_complete").wait(StackName=stack_name)
        return False
    return True


def ask_for_token(exists: bool) -> str | None:
    """Returns the token, or None to keep the stored one (only possible on update)."""
    prompt = "Todoist API token (Enter to keep the current one): " if exists else "Todoist API token (input hidden): "
    token = getpass.getpass(prompt).strip()
    if not token and not exists:
        raise SystemExit("A Todoist token is required. Find it in Todoist: Settings -> Integrations -> Developer.")
    if token:
        ok, message = check_todoist_token(token)
        print(("OK: " if ok else "WARNING: ") + message)
        if not ok and input("Deploy anyway? [y/N] ").strip().lower() != "y":
            raise SystemExit("Stopped. Fix the token and run again.")
    return token or None


def build_parameters(token: str | None) -> list[dict]:
    if token:
        return [{"ParameterKey": "TodoistToken", "ParameterValue": token}]
    return [{"ParameterKey": "TodoistToken", "UsePreviousValue": True}]


def deploy(cfn, config: dict, token: str | None, exists: bool) -> None:
    stack = config["stack_name"]
    change_set = "study-assistant-deploy"
    cfn.create_change_set(
        StackName=stack, ChangeSetName=change_set, ChangeSetType="UPDATE" if exists else "CREATE",
        TemplateBody=TEMPLATE.read_text(encoding="utf-8"), Parameters=build_parameters(token),
        Capabilities=["CAPABILITY_IAM"],  # we create an IAM role (the Lambda's)
    )
    try:
        cfn.get_waiter("change_set_create_complete").wait(StackName=stack, ChangeSetName=change_set)
    except WaiterError:
        reason = cfn.describe_change_set(StackName=stack, ChangeSetName=change_set)["StatusReason"]
        cfn.delete_change_set(StackName=stack, ChangeSetName=change_set)
        if "didn't contain changes" in reason or "No updates" in reason:
            print("Stack is already up to date.")
            return
        raise SystemExit(f"Change set failed: {reason}")

    print("Deploying (takes 1-2 minutes) ...")
    cfn.execute_change_set(StackName=stack, ChangeSetName=change_set)
    waiter = cfn.get_waiter("stack_update_complete" if exists else "stack_create_complete")
    try:
        waiter.wait(StackName=stack, WaiterConfig={"Delay": 5, "MaxAttempts": 120})
    except WaiterError:
        raise SystemExit(describe_failures(cfn, stack))


def describe_failures(cfn, stack_name: str) -> str:
    """Collect the CREATE_FAILED / UPDATE_FAILED reasons so students see *why* it failed."""
    events = cfn.describe_stack_events(StackName=stack_name)["StackEvents"]
    lines = [f"- {e['LogicalResourceId']}: {e.get('ResourceStatusReason', '')}"
             for e in events if e["ResourceStatus"].endswith("_FAILED") and e.get("ResourceStatusReason")]
    reasons = "\n".join(dict.fromkeys(reversed(lines))) or "(no reason reported)"
    return f"Deployment failed:\n{reasons}\nMore detail: Events tab of the stack in the CloudFormation console."


def save_outputs(cfn, config: dict) -> None:
    outputs = cfn.describe_stacks(StackName=config["stack_name"])["Stacks"][0].get("Outputs", [])
    for output in outputs:
        if output["OutputKey"] in OUTPUT_TO_CONFIG:
            config[OUTPUT_TO_CONFIG[output["OutputKey"]]] = output["OutputValue"]
    save_config(config)


def main() -> None:
    config = load_config()
    cfn = boto3.client("cloudformation", region_name=config["region"])
    exists = stack_exists(cfn, config["stack_name"])
    token = ask_for_token(exists)
    deploy(cfn, config, token, exists)
    save_outputs(cfn, config)
    print("Stack outputs saved to config.json. Pushing Lambda code ...")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "deploy_lambda.py")], check=True)
    print("\nDone. Next: streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
