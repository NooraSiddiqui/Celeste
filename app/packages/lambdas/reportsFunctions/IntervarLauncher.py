import json
import logging
import os
import re
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


print("Loading function", flush=True)

client = boto3.client("batch")
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    s3_event = parse_event(event)
    bucket = s3_event["Records"][0]["s3"]["bucket"]["name"]
    key = s3_event["Records"][0]["s3"]["object"]["key"]
    logger.info("Processing event for {0} in bucket '{1}'".format(key, bucket))

    if is_intervar_file(key):
        inputfile = "s3://{0}/{1}".format(bucket, key)
        key_dir = os.path.dirname(key) #liftover folder
        outkey_prefix = os.path.dirname(key_dir) #sample folder
        key_basename = os.path.basename(key)
        outkey_file = os.path.splitext(key_basename)[0]
        safeName = getSafeName(Path(key).stem)
        jobName = "intervar_" + safeName
        command = intervar(bucket, inputfile, outkey_prefix, outkey_file)
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="intervar-queue-prod",
                jobDefinition="intervar-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "AoU", "user": "lambda", "hgsccl:purpose": "intervar", "hgsccl:env": "prod"},
                propagateTags=True,
                containerOverrides={"command": command},
            )
            # Logs Batch submit_job response
            logger.info("Response: " + json.dumps(response, indent=2))
            logger.info("Job queued for {0}: {1}".format(key, response["jobId"]))
        except ClientError as e:
            logger.error(e.response["Error"]["Message"])
    else:
        logger.info(
            "key: {} in bucket: {} not a preprocessed hard-filtered.vcf file. No job submitted.".format(
                key, bucket
            )
        )
        return "done"


def parse_event(event):
    record = event["Records"][0]
    if "EventSource" in record and record["EventSource"] == "aws:sns":
        message = record["Sns"]["Message"]
        if type(message) is not str:
            # if configured json test events happen to be type dict, returns as is
            return message
        else:
            return json.loads(message)  # SNS event str to object
    else:
        raise ValueError("Function only supports input from events with a source type of: aws.sns")


def getSafeName(input):
    return re.sub(r"[^\w]", "_", input)[:100]


def is_intervar_file(key):
    filename = key.split("/")[-1]
    return filename.startswith("Liftover_Preprocessing_Intersect_") and key.endswith(".hard-filtered.vcf") and "/fastqs/" not in key


def intervar(bucket, inputfile, outkey_prefix, outkey_file):
    out = "s3://{0}/{1}/Intervar_{2}".format(bucket, outkey_prefix, outkey_file)
    command = [
        "--buildver",
        "hg19",
        "--input",
        inputfile,
        "--input_type=VCF",
        "--output",
        out
    ]
    logger.info("Batch job command:{0}".format(command))
    return command
