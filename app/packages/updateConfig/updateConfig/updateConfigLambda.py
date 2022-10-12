import json
import boto3
import cfnresponse
import botocore

s3 = boto3.resource("s3", config=boto3.session.Config(signature_version="s3v4"))


def create(properties, physical_id):
    message = "Create Complete"
    print(message)
    return cfnresponse.SUCCESS, None


def update(properties, physical_id):
    return create(properties, physical_id)


def delete(properties, physical_id):
    region = properties["Region"]
    bucket = properties["Bucket"]
    deleteAll(bucket)
    print("success")
    return cfnresponse.SUCCESS, physical_id


def deleteAll(bucket):
    bucket_resource = s3.Bucket(bucket)
    print("\n[INFO]: Working on bucket [" + str(bucket) + "]")
    bucket_resource = s3.Bucket(bucket)
    print("[INFO]: Getting and deleting all object versions")
    try:
        object_versions = bucket_resource.object_versions.all()
        for object_version in object_versions:
            object_version.delete()    # TODO: Delete sets of 1000 object versions to reduce delete requests
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "AccessDenied":
            print("[WARNING]: Unable to delete object versions. (AccessDenied)")
        if e.response["Error"]["Code"] == "NoSuchBucket":
            print("[WARNING]: Unable to get versions. (NoSuchBucket)")
        else:
            print(e)


def handler(event, context):
    print("Received event: %s" % json.dumps(event))

    status = cfnresponse.FAILED
    new_physical_id = None

    try:
        properties = event.get("ResourceProperties")
        physical_id = event.get("PhysicalResourceId")

        status, new_physical_id = {
            "Create": create,
            "Update": update,
            "Delete": delete,
        }.get(event["RequestType"], lambda x, y: (cfnresponse.FAILED, None))(
            properties, physical_id
        )
    except Exception as e:
        print("Exception: %s" % e)
        status = cfnresponse.FAILED
    finally:
        cfnresponse.send(event, context, status, {}, new_physical_id)
