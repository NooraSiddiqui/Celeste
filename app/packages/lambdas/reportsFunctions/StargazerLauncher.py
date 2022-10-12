import json
import logging
import re
import os
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

    if is_liftover_file(key):
        inputfile = "s3://{0}/{1}".format(bucket, key)
        dragen_key = os.path.dirname(os.path.dirname(key)) + "/dragen/"
        gvcf_key = dragen_key + os.path.basename(key).replace('.vcf','.gvcf.gz').replace('Liftover_Preprocessing_Intersect_','').replace('CVL_PGX.','').replace('CVL_HDR.','')
        gvcf_index_key = dragen_key + os.path.basename(key).replace('.vcf','.gvcf.gz.tbi').replace('Liftover_Preprocessing_Intersect_','').replace('CVL_PGX.','').replace('CVL_HDR.','')
        gvcf = "s3://{0}/{1}".format(bucket, gvcf_key)
        gvcf_index = "s3://{0}/{1}".format(bucket, gvcf_index_key)
        outkey_file = Path(key).name
        outkey_prefix = Path(key).parents[1]
        safeName = getSafeName(Path(key).stem)
        jobName = "Stargazer_" + safeName
        command = stargazer(bucket, inputfile, outkey_prefix, outkey_file,gvcf,gvcf_index)
        try:
            response = client.submit_job(
                jobName=jobName,
                jobQueue="reports-queue-prod",
                jobDefinition="stargazer-prod",
                parameters= {"project": "AoU", "user": "lambda", "hgsccl:env": "prod"},
                tags={"hgsccl:project": "AoU", "user": "lambda", "hgsccl:purpose": "stargazer", "hgsccl:env": "prod"},
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


def is_liftover_file(key):
    if "CVL_HDR" in key:
        return False
    filename = key.split("/")[-1]
    return filename.startswith("Liftover_Preprocessing_Intersect_") and key.endswith(".hard-filtered.vcf") and "/fastqs/" not in key


def stargazer(bucket, inputfile, outkey_prefix, outkey_file,gvcf,gvcf_index):
    output_dir = "s3://{0}/{1}/stargazer/".format(bucket, outkey_prefix)
    outname = "Stargazer_{0}".format(outkey_file)
    command = [
        "--vcf",
        inputfile,
        "-t",
        "all",
        "--data",
        "wgs",
        "--output_dir",
        output_dir,
        "-o",
        outname,
        "--gvcf",
        gvcf, 
        "--gvcf_index", 
        gvcf_index,
        "--pgx_bed",
        "s3://hgsccl-op-data/Liftover_resources/stargazer/PGx.bed",
        "--grch38_fasta", 
        "s3://hgsccl-op-data/bwa_references/h/grch38/GRCh38_full_analysis_set_plus_decoy_hla.fa",
        "--header",
        "s3://hgsccl-op-data/Liftover_resources/stargazer/header.hdr",
        "--pgx_bed_38",
        "s3://hgsccl-op-data/Liftover_resources/stargazer/PGx.grc38.bed"
    ]
    logger.info("Batch job command:{0}".format(command))
    return command
    
