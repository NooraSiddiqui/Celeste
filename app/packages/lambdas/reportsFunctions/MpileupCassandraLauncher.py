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

    if isCassandra(key) and isBam(bucket,key):  # only submit batch job if file .vcf.gz file is present with BAM
        vcf = "s3://{0}/{1}".format(bucket, key) #.vcf.gz
        bamfile_key = getBam(bucket,key)
        bamfile = "s3://{0}/{1}".format(bucket, bamfile_key)
        outkey_file = Path(key).stem
        outkey_prefix = Path(key).parents[1]
        out = "s3://{0}/{1}/cassandra/".format(
            bucket, outkey_prefix
        )
        safeName = getSafeName(outkey_file)
        jobName = "mpileup_cassandra_" + safeName
        command = [
            "-f",
            "s3://hgsccl-op-data/bwa_references/h/hs37d5/hs37d5.fa",
            "-l",
            vcf,
            "-b",
            bamfile,
            "-o",
            out
        ]
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="intervar-queue-prod",
                jobDefinition="aws-mpileup-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "niaid", "user": "lambda", "hgsccl:purpose": "mpileup", "hgsccl:env": "prod"},
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
    
    elif isBam2(key) and isVcf(bucket,key): #BAM was loaded after hard-filtered vcf
        bamfile = "s3://{0}/{1}".format(bucket, key) #.bam
        vcffile_key = getVcf(bucket,key)
        vcf = "s3://{0}/{1}".format(bucket, vcffile_key)
        outkey_file = Path(key).stem
        outkey_prefix = Path(key).parents[1]
        out = "s3://{0}/{1}/cassandra/".format(
            bucket, outkey_prefix
        )
        safeName = getSafeName(outkey_file)
        jobName = "mpileup_cassandra_" + safeName
        command = [
            "-f",
            "s3://hgsccl-op-data/bwa_references/h/hs37d5/hs37d5.fa",
            "-l",
            vcf,
            "-b",
            bamfile,
            "-o",
            out
        ]
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="intervar-queue-prod",
                jobDefinition="aws-mpileup-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
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
            "key: {} in bucket: {} not vcf.gz file or both files (hard-filtered vcf & bam) not found. No reports submitted.".format(
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


def isCassandra(key):
    suffix = (".hard-filtered.vcf.gz")
    if key.endswith(suffix):
        return True
    else:
        return False

def isBam(bucket, key):
    outkey_prefix = Path(key).parents[1]
    prefix = "s3://{0}/{1}".format(bucket, outkey_prefix)
    key_prefix_str = str(outkey_prefix)

    fileFound = False
    #fileConditionFound = False
    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        if obj['Key'].endswith(".bam") :
            fileFound = True
    if fileFound: 
        return True
    return False

def isBam2(key):
    suffix = (".bam")
    if key.endswith(suffix):
        return True
    else:
        return False

def getBam(bucket, key):
    outkey_prefix = Path(key).parents[1]
    prefix = "s3://{0}/{1}".format(bucket, outkey_prefix)
    key_prefix_str = str(outkey_prefix)

    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        if obj['Key'].endswith(".bam") :
            bamfile = obj['Key']
    return bamfile
    
def isVcf(bucket, key):
    outkey_prefix = Path(key).parents[1]
    prefix = "s3://{0}/{1}".format(bucket, outkey_prefix)
    key_prefix_str = str(outkey_prefix)

    fileFound = False
    #fileConditionFound = False
    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        if obj['Key'].endswith(".hard-filtered.vcf.gz") :
            fileFound = True
    if fileFound: 
        return True
    return False

def getVcf(bucket, key):
    outkey_prefix = Path(key).parents[1]
    prefix = "s3://{0}/{1}".format(bucket, outkey_prefix)
    key_prefix_str = str(outkey_prefix)

    theObjs = s3client.list_objects_v2(Bucket=bucket, Prefix=key_prefix_str)

    for obj in theObjs['Contents']:
        if obj['Key'].endswith(".hard-filtered.vcf.gz") :
            bamfile = obj['Key']
    return bamfile
