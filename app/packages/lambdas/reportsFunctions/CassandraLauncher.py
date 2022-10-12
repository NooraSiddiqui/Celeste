import json
import logging
import re
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


print("Loading function", flush=True)

client = boto3.client("batch")
s3client = boto3.client("s3")
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    s3_event = parse_event(event)
    bucket = s3_event["Records"][0]["s3"]["bucket"]["name"]
    key = s3_event["Records"][0]["s3"]["object"]["key"]
    logger.info("Processing event for {0} in bucket '{1}'".format(key, bucket))

    if isPileup(key) and isVcf(bucket,key):  # only submit batch job if file SAMTOOLS_pileup file is present with .vcf.gz
        pileupFile = "s3://{0}/{1}".format(bucket, key) #.SAMTOOLS_pileup
        vcffile_key = getVcf(bucket,key)
        vcffile = "s3://{0}/{1}".format(bucket, vcffile_key)
        outkey_file = Path(key).stem
        outkey_prefix = Path(key).parents[1]
        out = "s3://{0}/{1}/cassandra/".format(
            bucket, outkey_prefix
        )
        safeName = getSafeName(outkey_file)
        jobName = "cassandra_" + safeName
        command = [
            "-i", 
            vcffile, 
            "-p", 
            pileupFile,
            "-o", 
            out
        ]
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="intervar-queue-prod",
                jobDefinition="cassandra-cassandra-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "niaid", "user": "lambda", "hgsccl:purpose": "cassandra", "hgsccl:env": "prod"},
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
            "key: {} in bucket: {} not pileup file. No reports submitted.".format(
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


def isPileup(key):
    suffix = (".SAMTOOLS_pileup")
    if key.endswith(suffix):
        return True
    else:
        return False

def isVcf(bucket, key):
    pileup_prefix = Path(key).parents[1]
    outkey_prefix = Path(pileup_prefix).parents[1]
    prefix = "s3://{0}/{1}/dragen/".format(bucket, outkey_prefix)
    key_prefix_str = str(pileup_prefix)

    fileFound = False
    #fileConditionFound = False
    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        #if object['Key'].endswith(fileN+'_condition.jpg') :
            #fileConditionFound = True
        if obj['Key'].endswith(".hard-filtered.vcf.gz") :
            fileFound = True
    if fileFound: 
        return True
    return False

def getVcf(bucket, key):
    pileup_prefix = Path(key).parents[1]
    outkey_prefix = Path(pileup_prefix).parents[1]
    prefix = "s3://{0}/{1}/dragen/".format(bucket, outkey_prefix)
    key_prefix_str = str(pileup_prefix)


    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        #if object['Key'].endswith(fileN+'_condition.jpg') :
            #fileConditionFound = True
        if obj['Key'].endswith(".hard-filtered.vcf.gz") :
            vcffile = obj['Key']
    return vcffile
