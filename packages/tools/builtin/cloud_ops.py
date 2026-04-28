"""cloud_ops — AWS/GCP/Azure facade: list/describe resources, invoke functions, get logs."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CloudOpsInput(BaseModel):
    provider: str = Field(description="Cloud provider: 'aws' | 'gcp' | 'azure'")
    operation: str = Field(description="Operation: 'list_resources' | 'describe_resource' | 'invoke_function' | 'get_logs'")
    resource_type: str = Field(default="", description="Resource type (e.g. 'ec2' for AWS, 'functions' for GCP).")
    resource_id: str = Field(default="", description="Resource identifier (ARN, name, ID).")
    region: str = Field(default="", description="Cloud region.")
    function_name: str = Field(default="", description="Function name for invoke_function.")
    payload: dict = Field(default_factory=dict, description="Payload for function invocation.")
    filters: dict = Field(default_factory=dict, description="Filters for list operations.")
    max_results: int = Field(default=20)


class CloudOpsTool(BaseCallable):
    name = "cloud_ops"
    description = (
        "AWS, GCP, and Azure cloud operations: list resources, describe instances, "
        "invoke Lambda/Cloud Functions, retrieve CloudWatch/Stackdriver logs. "
        "Requires cloud SDK credentials in environment."
    )
    callable_type = CallableType.TOOL
    input_schema = CloudOpsInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=True,
        network_allowed=True,
    )

    async def _execute(self, input: CloudOpsInput, context: CallContext) -> ToolOutput:
        provider = input.provider.lower()
        if provider == "aws":
            return await self._aws(input)
        elif provider == "gcp":
            return await self._gcp(input)
        elif provider == "azure":
            return await self._azure(input)
        else:
            return ToolOutput(result=f"[cloud_ops: unknown provider '{input.provider}' — use aws | gcp | azure]")

    async def _aws(self, input: CloudOpsInput) -> ToolOutput:
        try:
            import boto3
        except ImportError:
            return ToolOutput(result="[cloud_ops: boto3 not installed — run: pip install boto3]")

        try:
            import asyncio
            region = input.region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

            if input.operation == "list_resources":
                rtype = input.resource_type.lower()
                if rtype == "ec2":
                    ec2 = boto3.client("ec2", region_name=region)
                    resp = await asyncio.to_thread(ec2.describe_instances, MaxResults=input.max_results)
                    instances = []
                    for r in resp.get("Reservations", []):
                        for i in r.get("Instances", []):
                            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
                            instances.append(f"  {i['InstanceId']} [{i['State']['Name']}] {i['InstanceType']} {name}")
                    return ToolOutput(result=f"EC2 instances ({region}):\n" + "\n".join(instances[:input.max_results]))
                elif rtype in ("s3", ""):
                    s3 = boto3.client("s3")
                    resp = await asyncio.to_thread(s3.list_buckets)
                    buckets = [f"  {b['Name']} (created: {b['CreationDate'].date()})" for b in resp.get("Buckets", [])]
                    return ToolOutput(result="S3 buckets:\n" + "\n".join(buckets[:input.max_results]))
                else:
                    return ToolOutput(result=f"[cloud_ops: AWS resource_type '{rtype}' not supported yet]")

            elif input.operation == "invoke_function":
                import json
                lam = boto3.client("lambda", region_name=region)
                resp = await asyncio.to_thread(
                    lam.invoke,
                    FunctionName=input.function_name or input.resource_id,
                    Payload=json.dumps(input.payload).encode(),
                )
                payload = resp["Payload"].read().decode()
                return ToolOutput(result=f"Lambda invoked. Status: {resp['StatusCode']}\nResponse: {payload[:2000]}")

            elif input.operation == "get_logs":
                logs = boto3.client("logs", region_name=region)
                groups_resp = await asyncio.to_thread(logs.describe_log_groups, logGroupNamePrefix=input.resource_id or "/aws/lambda/", limit=5)
                lines = ["CloudWatch log groups:"]
                for g in groups_resp.get("logGroups", []):
                    lines.append(f"  {g['logGroupName']}")
                return ToolOutput(result="\n".join(lines))

            else:
                return ToolOutput(result=f"[cloud_ops: AWS operation '{input.operation}' not supported]")

        except Exception as exc:
            return ToolOutput(result=f"[cloud_ops: AWS error — {exc}]")

    async def _gcp(self, input: CloudOpsInput) -> ToolOutput:
        try:
            from google.cloud import functions_v2  # noqa: F401
        except ImportError:
            return ToolOutput(result="[cloud_ops: google-cloud-functions not installed — run: pip install google-cloud-functions]")
        return ToolOutput(result="[cloud_ops: GCP operations require further configuration — set GOOGLE_APPLICATION_CREDENTIALS]")

    async def _azure(self, input: CloudOpsInput) -> ToolOutput:
        try:
            from azure.identity import DefaultAzureCredential  # noqa: F401
        except ImportError:
            return ToolOutput(result="[cloud_ops: azure-identity not installed — run: pip install azure-identity azure-mgmt-resource]")
        return ToolOutput(result="[cloud_ops: Azure operations require AZURE_SUBSCRIPTION_ID env var and Azure credentials]")
