"""Zip the lambda/ folder in memory and push it to the deployed function.

Run this after editing anything in lambda/. It is safe to run any number of times.
We build the zip with Python's zipfile module so it works on Windows, macOS and
Linux without needing a `zip` command.
"""
import io
import zipfile

import boto3

from common import ROOT, load_config

LAMBDA_DIR = ROOT / "lambda"


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(LAMBDA_DIR.glob("*.py")):
            archive.write(path, arcname=path.name)  # files must sit at the zip root
    return buffer.getvalue()


def main() -> None:
    config = load_config()
    name = config.get("lambda_function_name")
    if not name:
        raise SystemExit("No lambda_function_name in config.json. Run scripts/deploy_stack.py first.")
    client = boto3.client("lambda", region_name=config["region"])
    print(f"Uploading code to {name} ...")
    client.update_function_code(FunctionName=name, ZipFile=build_zip())
    client.get_waiter("function_updated_v2").wait(FunctionName=name)  # wait until the new code is live
    print("Lambda code updated.")


if __name__ == "__main__":
    main()
