"""Pre-flight check: is this machine ready for the workshop?

Prints a tick or a cross for each requirement, with a hint on how to fix
anything red. Safe to run any time; the only AWS call that costs anything is
one tiny model request (a fraction of a cent).
"""
import getpass
import importlib.metadata
import sys

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from common import check_todoist_token, load_config

MIN_PYTHON = (3, 10)


def report(ok: bool, message: str, fix: str = "") -> bool:
    print(("✅ " if ok else "❌ ") + message)
    if not ok and fix:
        print(f"   Fix: {fix}")
    return ok


def check_python() -> bool:
    version = ".".join(map(str, sys.version_info[:3]))
    return report(sys.version_info >= MIN_PYTHON, f"Python {version}", "Install Python 3.10 or newer.")


def check_libraries() -> bool:
    ok = True
    for name in ("boto3", "streamlit"):
        try:
            report(True, f"{name} {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            ok = report(False, f"{name} is not installed", "pip install -r requirements.txt")
    return ok


def check_credentials(region: str) -> bool:
    try:
        identity = boto3.client("sts", region_name=region).get_caller_identity()
    except (BotoCoreError, ClientError) as error:
        return report(False, f"AWS credentials: {error}", "Run `aws configure` with your access key.")
    return report(True, f"AWS credentials work (account {identity['Account']})")


def check_region(config: dict) -> bool:
    configured = boto3.session.Session().region_name
    if configured and configured != config["region"]:
        return report(False, f"AWS CLI region is {configured} but config.json says {config['region']}",
                      "Make them match: edit config.json or run `aws configure set region " + config["region"] + "`.")
    return report(True, f"Region {config['region']}")


def check_model_access(config: dict) -> bool:
    runtime = boto3.client("bedrock-runtime", region_name=config["region"])
    try:
        runtime.converse(modelId=config["model_id"], messages=[{"role": "user", "content": [{"text": "Say hi"}]}],
                         inferenceConfig={"maxTokens": 10})
    except (BotoCoreError, ClientError) as error:
        return report(False, f"Model {config['model_id']}: {error}",
                      "Bedrock console -> Model access: enable the model in this region.")
    return report(True, f"Bedrock model access for {config['model_id']}")


def check_lambda(config: dict) -> bool:
    name = config.get("lambda_function_name")
    if not name:
        print("⏭️  Tools Lambda not deployed yet: that is fine, we deploy it together in the workshop")
        return True
    try:
        boto3.client("lambda", region_name=config["region"]).get_function_configuration(FunctionName=name)
    except (BotoCoreError, ClientError) as error:
        return report(False, f"Lambda {name}: {error}", "Run `python scripts/deploy_stack.py`.")
    return report(True, f"Tools Lambda {name} is deployed")


def check_todoist() -> bool:
    token = getpass.getpass("Paste your Todoist token to test it (input hidden, Enter to skip): ").strip()
    if not token:
        print("⏭️  Todoist token check skipped")
        return True
    ok, message = check_todoist_token(token)  # the token is used for this check only, never saved
    return report(ok, message, "Copy it again from Todoist: Settings -> Integrations -> Developer.")


def main() -> None:
    config = load_config()
    results = [check_python(), check_libraries(), check_credentials(config["region"])]
    if results[-1]:
        results += [check_region(config), check_model_access(config), check_lambda(config)]
    results.append(check_todoist())
    print("\nAll good!" if all(results) else "\nFix the ❌ items above, then run this again.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
