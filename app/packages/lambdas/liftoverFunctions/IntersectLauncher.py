import json
import logging
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

    if is_vcf_gz(key):
        inputfile = "s3://{0}/{1}".format(bucket, key)
        outkey_file = Path(key).stem.split(".hard-filtered.vcf")[0]
        outkey_prefix = Path(key).parents[1]
        safeName = getSafeName(outkey_file)
        jobName = "intersect_" + safeName
        ploidy = "s3://{0}/{1}/dragen/{2}.wgs_ploidy.csv".format(
            bucket, outkey_prefix, outkey_file
        )
        command = intersect(bucket, inputfile, outkey_prefix, ploidy)
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="reports-plus-queue-prod",
                jobDefinition="liftover-intersect-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "AoU", "user": "lambda", "hgsccl:purpose": "intersect", "hgsccl:env": "prod"},
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
            "key: {} in bucket: {} not a hard-filtered.vcf.gz file. No job submitted.".format(
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


def is_vcf_gz(key):
    return key.endswith(".hard-filtered.vcf.gz") and "/fastqs/" not in key


def intersect(bucket, inputfile, outkey_prefix, ploidy):
    out = "s3://{0}/{1}/liftover".format(bucket, outkey_prefix)
    command = [
        "-a",
        inputfile,
        "-o",
        out,
        "-p",
        ploidy,
        "-b",
        "s3://hgsccl-op-data/Liftover_resources/Bed_file/ACMG59_PGx.combined.grc38.annotated.bed",
    ]
    logger.info("Batch job command:{0}".format(command))
    return command
    
