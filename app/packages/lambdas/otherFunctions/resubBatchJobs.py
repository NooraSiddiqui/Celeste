import json
import logging
import re
from decimal import *

import boto3
from botocore.exceptions import ClientError


print("Loading function", flush=True)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
batch = boto3.client("batch")


def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    if event["source"] != "aws.batch":
       raise ValueError("Function only supports input from events with a source type of: aws.batch")
    detail = event["detail"]
    logger.info("Detail: %s", detail)
    if "stoppedAt" in detail and "startedAt" in detail:
        stoppedAt = detail["stoppedAt"]
        startedAt = detail["startedAt"]
        runtimeMinutes = Decimal(str((stoppedAt - startedAt)/(1000*60)))
    else:
        runtimeMinutes = Decimal(0)
    # dict can be saved as attributes in db
    d={
        'jobName': detail["jobName"],
        'jobId': detail["jobId"],
        'jobQueue': (detail["jobQueue"]).split("/")[1],
        'jobStatus': detail["status"],
        'statusReason' : detail["statusReason"],
        'jobDefinition': detail["jobDefinition"],
        'runtimeMinutes': runtimeMinutes,
        'jobDatetime': event["time"],
        'attempts': detail["attempts"],
        'container': detail["container"],
    }
    # If job parameters exist, add as unique attributes; use for "project" tags
    p = detail["parameters"]
    if p:
        d.update(p)
    # handle certain job failures, update d
    if detail["status"] == "FAILED":
        resubInterruption(d, p)
    d.pop("statusReason", None)
    return "done"


def resubInterruption(d, p):
    """ Checks reason for job failure and resubmits 
    Batch job for host instance termination.
    """
    logger.info("""Handling job failure.\n Previous job attempts : {0}\n 
        Final attempt exit message: {1}\n""".format(d["attempts"], d["statusReason"]))
    if hostTerminated(d["statusReason"]):
        new_jobName = getSafeName(d["jobName"])
        command = d["container"]["command"]
        try:
            response = batch.submit_job(
                jobName=new_jobName,
                jobQueue=d["jobQueue"],
                jobDefinition=d["jobDefinition"],
                parameters=p,
                containerOverrides={"command": command},
            )
            # track job handled status and new job name
            d.update({'newJobName': new_jobName, 'failHandled': "true"})
            logger.info("Batch submit job response: " + json.dumps(response, indent=2))
            logger.info("Job {0} submitted to Batch.\n Batch command: {1}".format(new_jobName, command))
        except ClientError as e:
            logger.error(e.response["Error"]["Message"])
            d.update({'failHandled': "false"})
            raise
    else:
        logger.info("This job is not viable for automated resubmission based on exit message.")
        d.update({'failHandled': "false"})
    return d
    

def hostTerminated(str):
    return re.search(r'^\bHost EC2\b.*\bterminated\b', str)


def getSafeName(input):
    x = re.sub(r"[^\w]", "_", input)[:90]
    return x + "_lambdaResub"
