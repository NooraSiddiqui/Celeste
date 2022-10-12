import json
import logging
import re

import boto3
from botocore.exceptions import ClientError


print("Loading function", flush=True)

s3_client = boto3.client("s3")
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    s3_event = parse_event(event)
    bucket = s3_event["Records"][0]["s3"]["bucket"]["name"]
    key = s3_event["Records"][0]["s3"]["object"]["key"]
    logger.info("Processing event for {0} in bucket '{1}'".format(key, bucket))
    tags = generate_tags(key, bucket)
    try:
        response = s3_client.put_object_tagging(
            Bucket=bucket, Key=key, Tagging=tags
        )
        # Logs response
        print("Response: " + json.dumps(response, indent=2))
    except ClientError as e:
        logger.error(e.response["Error"]["Message"])
        raise
    logger.info("Tags applied to {0}. Tagset: {1}".format(key, tags))
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


def generate_tags(key, bucket):
    archival_suffixes = (".cram", "vcf.gz", ".fastq.gz", ".hard-filtered_INDEL_Annotated.vcf", ".hard-filtered_SNP_Annotated.vcf")
    if key.endswith(archival_suffixes):
        tagset = {
            "TagSet": [
                {"Key": "hgsccl:archive", "Value": "yes"},
                {"Key": "hgsccl:cvl-delivered", "Value": "no"},
                {"Key": "hgsccl:drc-delivered", "Value": "no"},
                {"Key": "hgsccl:delete", "Value": "no"},
            ]
        }
    elif niaid_merge_bam(key, bucket):
        tagset = {
            "TagSet": [
                {"Key": "hgsccl:archive", "Value": "yes"},
                {"Key": "hgsccl:cvl-delivered", "Value": "no"},
                {"Key": "hgsccl:drc-delivered", "Value": "no"},
                {"Key": "hgsccl:delete", "Value": "no"},
            ]
        }
    elif key.endswith(".bam"):
        tagset = {
            "TagSet": [
                {"Key": "hgsccl:archive", "Value": "no"},
                {"Key": "hgsccl:cvl-delivered", "Value": "no"},
                {"Key": "hgsccl:drc-delivered", "Value": "no"},
                {"Key": "hgsccl:delete", "Value": "yes"},
            ]
        }
    else:
        tagset = {
            "TagSet": [
                {"Key": "hgsccl:archive", "Value": "no"},
                {"Key": "hgsccl:cvl-delivered", "Value": "no"},
                {"Key": "hgsccl:drc-delivered", "Value": "no"},
                {"Key": "hgsccl:delete", "Value": "no"},
            ]
        }
    return tagset


def dragen_log(key):
    return bool(re.search("dragen_log_(\d+).txt", key))


def niaid_merge_bam(key, bucket):
    mergesContainList = [ ".bam", "niaid", "merges"]
    s3path = "s3://%s/%s" % (bucket, key)
    if all([x in s3path for x in mergesContainList]):
        return True
    else:
        return False
