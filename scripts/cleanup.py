"""Delete everything this project created: the CloudFormation stack and its secret.

Run this at the end of the workshop so nothing keeps costing money. Safe to
run twice: anything already gone is skipped. Your Todoist tasks are untouched.
"""
import boto3
from botocore.exceptions import ClientError

from common import load_config, save_config

CLEARED_KEYS = ["lambda_function_name", "table_name", "todoist_secret_arn"]


def delete_stack(config: dict) -> None:
    cfn = boto3.client("cloudformation", region_name=config["region"])
    try:
        cfn.describe_stacks(StackName=config["stack_name"])
    except ClientError:
        print("Stack was already deleted.")
        return
    print("Deleting stack (1-2 minutes) ...")
    cfn.delete_stack(StackName=config["stack_name"])
    cfn.get_waiter("stack_delete_complete").wait(StackName=config["stack_name"])
    print("Stack deleted.")


def purge_secret(config: dict) -> None:
    """CloudFormation leaves a deleted secret in a 30-day recovery window; remove it for good."""
    arn = config.get("todoist_secret_arn")
    if not arn:
        return
    try:
        boto3.client("secretsmanager", region_name=config["region"]).delete_secret(SecretId=arn, ForceDeleteWithoutRecovery=True)
        print("Secret permanently deleted.")
    except ClientError:
        print("Secret already gone.")


def main() -> None:
    config = load_config()
    if input(f"Delete stack '{config['stack_name']}' in {config['region']}? [y/N] ").strip().lower() != "y":
        raise SystemExit("Nothing deleted.")
    delete_stack(config)
    purge_secret(config)
    for key in CLEARED_KEYS:
        config[key] = ""
    save_config(config)
    print("\nAll cleaned up. Nothing is left running.")


if __name__ == "__main__":
    main()
