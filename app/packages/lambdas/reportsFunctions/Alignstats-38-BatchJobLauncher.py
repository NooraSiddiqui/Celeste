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

    if isAlignment(key):  # only generate reports for alignment files e.g. bam
        inputfile = "s3://{0}/{1}".format(bucket, key)
        outkey_file = Path(key).stem
        # for compatibility with existing HgV protocol, adjust output dir to ../<where bamorcram is>
        outkey_prefix = Path(key).parents[1]
        out = "s3://{0}/{1}/reports/AlignStats/{2}.alignstats.json".format(
            bucket, outkey_prefix, outkey_file
        )
        safeName = getSafeName(outkey_file)
        jobName = "alignstats_" + safeName
        command = [
            "-v",
            "-i",
            inputfile,
            "-m",
            "s3://hgsccl-op-data/alignstats/masks/GRCh38_1000Genomes_N_regions.bed",
            "-o",
            out,
            "-C",
            "-r",
            "s3://hgsccl-op-data/alignstats/regions/GRCh38_full_analysis_set_plus_decoy_hla.bed",
            "-P",
            "1",
            "-F",
            "2048",
            "-b",
            "3",
            "-O"
        ]
        if inputfile.endswith(".cram"):
            command.extend(["-T", "s3://hgsccl-op-data/bwa_references/h/grch38/GRCh38_full_analysis_set_plus_decoy_hla.fa"])
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="reports-queue-prod",
                jobDefinition="reports-alignstats-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "AoU", "user": "lambda", "hgsccl:purpose": "alignstats", "hgsccl:env": "prod"},
                propagateTags=True,
                containerOverrides={"command": command},
            )
            # Logs Batch submit_job response
            print("Response: " + json.dumps(response, indent=2))
        except ClientError as e:
            logger.error(e.response["Error"]["Message"])
            raise
        logger.info("Job queued for {0}: {1}".format(key, response["jobId"]))
        return "done"
    else:
        logger.info(
            "key: {} in bucket: {} not alignment file. No reports submitted.".format(
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


def isAlignment(key):
    suffix = (".bam", ".cram")
    if key.endswith(suffix):
        return True
    else:
        return False
